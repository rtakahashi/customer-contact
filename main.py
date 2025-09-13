"""
このファイルは、Webアプリのメイン処理が記述されたファイルです。
"""
# ----- main.py の最上部（この上に他の import を置かない）-----
import sys, importlib

def ensure_sqlite335_or_newer():
    # まず標準sqlite3のバージョンを確認
    import sqlite3 as _std_sqlite3
    try:
        ver_tuple = tuple(map(int, _std_sqlite3.sqlite_version.split(".")))
    except Exception:
        ver_tuple = (0, 0, 0)

    if ver_tuple >= (3, 35, 0):
        # 十分新しい → 何もしない（ローカルは多くがこれ）
        print("[sqlite] using stdlib:", _std_sqlite3.sqlite_version, flush=True)
        return

    # 古い場合のみ pysqlite3 に差し替え（Cloud など）
    try:
        sqlite3 = importlib.import_module("pysqlite3.dbapi2")
        sys.modules["sqlite3"] = sqlite3
        sys.modules["sqlite3.dbapi2"] = sqlite3
        sys.modules["sqlite"] = sqlite3
        print("[sqlite] shimmed to pysqlite3:", sqlite3.sqlite_version, flush=True)
    except Exception as e:
        # ここに来るのは「古いのに pysqlite3 が入っていない」ケース
        raise RuntimeError(
            "sqlite3 < 3.35 かつ pysqlite3-binary 未導入です。"
            "requirements.txt に pysqlite3-binary を追加してください。"
        ) from e

ensure_sqlite335_or_newer()

import sys, os, traceback, logging
logging.basicConfig(level=logging.INFO)
print("BOOT: reached top of script", flush=True)

############################################################
# ライブラリの読み込み
############################################################
from dotenv import load_dotenv
import logging
import streamlit as st
import utils
from initialize import initialize
import components as cn
import constants as ct


############################################################
# 設定関連
############################################################
st.set_page_config(
    page_title=ct.APP_NAME
)

load_dotenv()

logger = logging.getLogger(ct.LOGGER_NAME)


############################################################
# 初期化処理
############################################################
try:
    initialize()
except Exception as e:
    logger.error(f"{ct.INITIALIZE_ERROR_MESSAGE}\n{e}")
    st.error(utils.build_error_message(ct.INITIALIZE_ERROR_MESSAGE), icon=ct.ERROR_ICON)
    st.stop()

# アプリ起動時のログ出力
if not "initialized" in st.session_state:
    st.session_state.initialized = True
    logger.info(ct.APP_BOOT_MESSAGE)


############################################################
# 初期表示
############################################################
# タイトル表示
cn.display_app_title()

# サイドバー表示
cn.display_sidebar()

# AIメッセージの初期表示
cn.display_initial_ai_message()


############################################################
# スタイリング処理
############################################################
# 画面装飾を行う「CSS」を記述
st.markdown(ct.STYLE, unsafe_allow_html=True)


############################################################
# チャット入力の受け付け
############################################################
chat_message = st.chat_input(ct.CHAT_INPUT_HELPER_TEXT)


############################################################
# 会話ログの表示
############################################################
try:
    cn.display_conversation_log(chat_message)
except Exception as e:
    logger.error(f"{ct.CONVERSATION_LOG_ERROR_MESSAGE}\n{e}")
    st.error(utils.build_error_message(ct.CONVERSATION_LOG_ERROR_MESSAGE), icon=ct.ERROR_ICON)
    st.stop()


############################################################
# チャット送信時の処理
############################################################
if chat_message:
    # ==========================================
    # 会話履歴の上限を超えた場合、受け付けない
    # ==========================================
    # ユーザーメッセージのトークン数を取得
    input_tokens = len(st.session_state.enc.encode(chat_message))
    # トークン数が、受付上限を超えている場合にエラーメッセージを表示
    if input_tokens > ct.MAX_ALLOWED_TOKENS:
        with st.chat_message("assistant", avatar=ct.AI_ICON_FILE_PATH):
            st.error(ct.INPUT_TEXT_LIMIT_ERROR_MESSAGE)
            st.stop()
    # トークン数が受付上限を超えていない場合、会話ログ全体のトークン数に加算
    st.session_state.total_tokens += input_tokens

    # ==========================================
    # 1. ユーザーメッセージの表示
    # ==========================================
    logger.info({"message": chat_message})

    res_box = st.empty()
    with st.chat_message("user", avatar=ct.USER_ICON_FILE_PATH):
        st.markdown(chat_message)
    
    # ==========================================
    # 2. LLMからの回答取得 or 問い合わせ処理
    # ==========================================
    res_box = st.empty()
    try:
        if st.session_state.contact_mode == ct.CONTACT_MODE_OFF:
            with st.spinner(ct.SPINNER_TEXT):
                result = utils.execute_agent_or_chain(chat_message)
        else:
            with st.spinner(ct.SPINNER_CONTACT_TEXT):
                result = utils.notice_slack(chat_message)
    except Exception as e:
        logger.error(f"{ct.MAIN_PROCESS_ERROR_MESSAGE}\n{e}")
        st.error(utils.build_error_message(ct.MAIN_PROCESS_ERROR_MESSAGE), icon=ct.ERROR_ICON)
        st.stop()
    
    # ==========================================
    # 3. 古い会話履歴を削除
    # ==========================================
    utils.delete_old_conversation_log(result)

    # ==========================================
    # 4. LLMからの回答表示
    # ==========================================
    with st.chat_message("assistant", avatar=ct.AI_ICON_FILE_PATH):
        try:
            cn.display_llm_response(result)

            logger.info({"message": result})
        except Exception as e:
            logger.error(f"{ct.DISP_ANSWER_ERROR_MESSAGE}\n{e}")
            st.error(utils.build_error_message(ct.DISP_ANSWER_ERROR_MESSAGE), icon=ct.ERROR_ICON)
            st.stop()
    
    # ==========================================
    # 5. 会話ログへの追加
    # ==========================================
    st.session_state.messages.append({"role": "user", "content": chat_message})
    st.session_state.messages.append({"role": "assistant", "content": result})


############################################################
# 6. ユーザーフィードバックのボタン表示
############################################################
if st.session_state.contact_mode == ct.CONTACT_MODE_OFF:
    cn.display_feedback_button()