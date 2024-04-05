import os
from typing import (Dict)
from cloud_sql.cloud_sql import CHAT_HISTORY_TABLE_NAME, init_connection_pool, create_sync_postgres_engine, CustomVectorStore
from google.cloud.sql.connector import Connector
from langchain_community.llms.huggingface_text_gen_inference import HuggingFaceTextGenInference
from langchain_community.embeddings.huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableParallel, RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_google_cloud_sql_pg import PostgresChatMessageHistory

QUESTION = "question"
HISTORY = "history"
CONTEXT = "context"

INFERENCE_ENDPOINT=os.environ.get('INFERENCE_ENDPOINT', '127.0.0.1:8081')
SENTENCE_TRANSFORMER_MODEL = 'intfloat/multilingual-e5-small' # Transformer to use for converting text chunks to vector embeddings


# TODO use a chat model instead of an LLM in the chain. Convert the prompt to a chat prompot template
# prompt = ChatPromptTemplate.from_messages(
#     [
#         ("system", """You help everyone by answering questions, and improve your answers from previous answers in history. 
#          You stick to the facts by basing your answers off of the context provided:"""),
#         MessagesPlaceholder(variable_name="history"),
#         MessagesPlaceholder(variable_name="context"),
#         ("human", "{question}"),
#     ]    
# )
template = """Answer the Question given by the user. Keep the answer to no more than 2 sentences. 
Improve upon your previous answers using History, a list of messages. 
Messages of type HumanMessage were asked by the user, and messages of type AIMessage were your previous responses.
Stick to the facts by basing your answers off of the Context provided.
Be brief in answering.
History: {""" + HISTORY + "}\n\nContext: {" + CONTEXT + "}\n\nQuestion: {" + QUESTION + "}\n"

prompt = PromptTemplate(template=template, input_variables=[HISTORY, CONTEXT, QUESTION])

engine = create_sync_postgres_engine()
chat_history_map: Dict[str, PostgresChatMessageHistory] = {}
def get_chat_history(session_id: str) -> PostgresChatMessageHistory:
    history = None
    if session_id in chat_history_map:
        history = chat_history_map[session_id]
    else:
        history = PostgresChatMessageHistory.create_sync(
            engine,
            session_id=session_id,
            table_name = CHAT_HISTORY_TABLE_NAME
        )
        chat_history_map[session_id] = history
    return history

def clear_chat_history(session_id: str):
    if session_id in chat_history_map:
        history = chat_history_map[session_id]
        history.clear()
        del chat_history_map[session_id]

#TODO: limit number of tokens in prompt to MAX_INPUT_LENGTH 
# (as specified in hugging face TGI input parameter)

def create_chain() -> RunnableWithMessageHistory: 
    # TODO HuggingFaceTextGenInference class is deprecated. 
    # The warning is: 
    #                The class `langchain_community.llms.huggingface_text_gen_inference.HuggingFaceTextGenInference` 
    #                was deprecated in langchain-community 0.0.21 and will be removed in 0.2.0. Use HuggingFaceEndpoint instead
    #The replacement is HuggingFace Endoint, which requires a huggingface
    # hub API token. Either need to add the token to the environment, or need to find a method to call TGI
    # without the token.
    # Example usage of HuggingFaceEndpoint:
    # llm = HuggingFaceEndpoint(
    #                 endpoint_url=f'http://{INFERENCE_ENDPOINT}/',
    #                 max_new_tokens=512,
    #                 top_k=10,
    #                 top_p=0.95,
    #                 typical_p=0.95,
    #                 temperature=0.01,
    #                 repetition_penalty=1.03,
    #                 huggingfacehub_api_token="my-api-key"
    #             )
    model = HuggingFaceTextGenInference(
        inference_server_url=f'http://{INFERENCE_ENDPOINT}/',
        max_new_tokens=512,
        top_k=10,
        top_p=0.95,
        typical_p=0.95,
        temperature=0.01,
        repetition_penalty=1.03,
    )

    langchain_embed = HuggingFaceEmbeddings(model_name=SENTENCE_TRANSFORMER_MODEL)
    vector_store = CustomVectorStore(langchain_embed, init_connection_pool(Connector()))
    retriever = vector_store.as_retriever()
    def get_question(question: dict) -> str:
        return question[QUESTION]
    question_getter = RunnableLambda(get_question)

    def get_history(history: dict) -> str:
        return history[HISTORY]
    history_getter = RunnableLambda(get_history)

    setup_and_retrieval = RunnableParallel(
        {"context": retriever, QUESTION: question_getter, HISTORY: history_getter}
    )
    chain = setup_and_retrieval | prompt | model
    chain_with_history = RunnableWithMessageHistory(
        chain,
        get_chat_history,
        input_messages_key=QUESTION,
        history_messages_key=HISTORY,
        output_messages_key="output"
    )
    return chain_with_history

def take_chat_turn(chain: RunnableWithMessageHistory, session_id: str, query_text: str) -> str:
    #TODO limit the number of history messages
    config = {"configurable": {"session_id": session_id}}
    result = chain.invoke({"question": query_text}, config)
    return str(result)