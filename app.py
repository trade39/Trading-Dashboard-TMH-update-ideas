# app.py - Main Entry Point for Multi-Page Trading Performance Dashboard
import streamlit as st
import pandas as pd
import numpy as np
import logging
import sys
import os
import datetime
import base64
from io import BytesIO

# --- SQLAlchemy Imports for DB connection ---
from sqlalchemy import create_engine
# sessionmaker is used within AuthService, not directly here usually

# --- MODIFICATION START: st.set_page_config() moved to the top ---
from config import APP_TITLE as PAGE_CONFIG_APP_TITLE
LOGO_PATH_FOR_BROWSER_TAB = "assets/Trading_Mastery_Hub_600x600.png"

st.set_page_config(
    page_title=PAGE_CONFIG_APP_TITLE,
    page_icon=LOGO_PATH_FOR_BROWSER_TAB,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/trade39/Trading-Dashboard-Advance-Test-5.4', # Replace
        'Report a bug': "https://github.com/trade39/Trading-Dashboard-Advance-Test-5.4/issues", # Replace
        'About': f"## {PAGE_CONFIG_APP_TITLE}\n\nA comprehensive dashboard for trading performance analysis."
    }
)
# --- MODIFICATION END ---

# --- Utility Modules ---
try:
    from utils.logger import setup_logger
    from utils.common_utils import load_css, display_custom_message, log_execution_time
except ImportError as e:
    st.error(f"Fatal Error: Could not import utility modules. App cannot start. Details: {e}")
    logging.basicConfig(level=logging.ERROR)
    logging.error(f"Fatal Error importing utils: {e}", exc_info=True)
    st.stop()

# --- Component Modules ---
try:
    from components.sidebar_manager import SidebarManager
    from components.column_mapper_ui import ColumnMapperUI
    from components.scroll_buttons import ScrollButtons
except ImportError as e:
    st.error(f"Fatal Error: Could not import component modules. App cannot start. Details: {e}")
    logging.error(f"Fatal Error importing components: {e}", exc_info=True)
    st.stop()

# --- Service Modules ---
try:
    from services.data_service import DataService, get_benchmark_data_static
    from services.analysis_service import AnalysisService
    from services.auth_service import AuthService # AuthService now uses DB
except ImportError as e:
    st.error(f"Fatal Error: Could not import service modules. App cannot start. Details: {e}")
    logging.error(f"Fatal Error importing services: {e}", exc_info=True)
    st.stop()

# --- Core Application Modules (Configs) ---
try:
    from config import (
        APP_TITLE, CONCEPTUAL_COLUMNS, CRITICAL_CONCEPTUAL_COLUMNS,
        CONCEPTUAL_COLUMN_TYPES, CONCEPTUAL_COLUMN_SYNONYMS,
        CONCEPTUAL_COLUMN_CATEGORIES,
        RISK_FREE_RATE, LOG_FILE, LOG_LEVEL, LOG_FORMAT,
        DEFAULT_BENCHMARK_TICKER, AVAILABLE_BENCHMARKS, EXPECTED_COLUMNS
    )
    from kpi_definitions import KPI_CONFIG
except ImportError as e:
    st.error(f"Fatal Error: Could not import configuration (config.py or kpi_definitions.py). App cannot start. Details: {e}")
    APP_TITLE = "TradingAppError"; LOG_FILE = "logs/error_app.log"; LOG_LEVEL = "ERROR"; LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    RISK_FREE_RATE = 0.02; CONCEPTUAL_COLUMNS = {"date": "Date", "pnl": "PnL"}; CRITICAL_CONCEPTUAL_COLUMNS = ["date", "pnl"]
    CONCEPTUAL_COLUMN_TYPES = {}; CONCEPTUAL_COLUMN_SYNONYMS = {}; KPI_CONFIG = {}; CONCEPTUAL_COLUMN_CATEGORIES = {}
    EXPECTED_COLUMNS = {"date": "date", "pnl": "pnl"}; DEFAULT_BENCHMARK_TICKER = "SPY"; AVAILABLE_BENCHMARKS = {}
    st.stop()

logger = setup_logger(
    logger_name=APP_TITLE, log_file=LOG_FILE, level=LOG_LEVEL, log_format=LOG_FORMAT
)
logger.info(f"Application '{APP_TITLE}' starting. Logger initialized.")

# --- Database Engine Setup for SQLite ---
# For Google Colab:
# If you want the DB to persist across sessions, mount Google Drive first:
# from google.colab import drive
# drive.mount('/content/drive')
# SQLITE_DB_PATH = "/content/drive/My Drive/your_app_folder/trading_hub_users.db" # Example for GDrive
# os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True) # Ensure directory exists

# For local execution or temporary Colab storage:
SQLITE_DB_PATH = "trading_hub_users.db" # Will be created in the current working directory

DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH}"
logger.info(f"Using SQLite database at: {SQLITE_DB_PATH}")

try:
    # For SQLite with Streamlit (which can be multi-threaded),
    # it's crucial to set check_same_thread=False.
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    logger.info(f"Database engine created for: {engine.url}")
except Exception as e:
    logger.critical(f"Failed to create database engine for SQLite URL '{DATABASE_URL}': {e}", exc_info=True)
    st.error(f"Fatal Error: Could not establish SQLite database connection. Error: {e}")
    st.stop()

# --- Initialize Authentication Service with DB Engine ---
try:
    auth_service = AuthService(db_engine=engine)
except Exception as e:
    logger.critical(f"Failed to initialize AuthService with the database engine: {e}", exc_info=True)
    st.error(f"Fatal Error: AuthService could not be initialized. Database issue likely. Error: {e}")
    st.stop()


# --- Theme Management ---
if 'current_theme' not in st.session_state:
    st.session_state.current_theme = "dark"
theme_js = f"""
<script>
    const currentTheme = '{st.session_state.current_theme}';
    document.documentElement.setAttribute('data-theme', currentTheme);
    if (currentTheme === "dark") {{
        document.body.classList.add('dark-mode');
        document.body.classList.remove('light-mode');
    }} else {{
        document.body.classList.add('light-mode');
        document.body.classList.remove('dark-mode');
    }}
</script>
"""
st.components.v1.html(theme_js, height=0)

# Load CSS
try:
    css_file_path = "style.css"
    if os.path.exists(css_file_path):
        load_css(css_file_path)
    else:
        logger.error(f"style.css not found at '{css_file_path}'.")
except Exception as e:
    logger.error(f"Failed to load style.css: {e}", exc_info=True)


# --- Initialize Session State ---
default_session_state = {
    'app_initialized': True, 'processed_data': None, 'filtered_data': None,
    'kpi_results': None, 'kpi_confidence_intervals': {},
    'risk_free_rate': RISK_FREE_RATE, 'uploaded_file_name': None,
    'uploaded_file_bytes_for_mapper': None, 'last_processed_file_id': None,
    'user_column_mapping': None, 'column_mapping_confirmed': False,
    'csv_headers_for_mapping': None, 'last_uploaded_file_for_mapping_id': None,
    'last_applied_filters': None, 'sidebar_filters': None, 'active_tab': "📈 Overview",
    'selected_benchmark_ticker': DEFAULT_BENCHMARK_TICKER,
    'selected_benchmark_display_name': next((n for n, t in AVAILABLE_BENCHMARKS.items() if t == DEFAULT_BENCHMARK_TICKER), "None"),
    'benchmark_daily_returns': None, 'initial_capital': 100000.0,
    'last_fetched_benchmark_ticker': None, 'last_benchmark_data_filter_shape': None,
    'last_kpi_calc_state_id': None,
    'max_drawdown_period_details': None,
    'authenticated': False, 'username': None, 'login_error': None,
    'registration_message': None, 'show_registration_form': False
}
for key, value in default_session_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

data_service = DataService()
analysis_service_instance = AnalysisService()

# --- LOGIN / REGISTRATION UI FUNCTION ---
def show_auth_ui():
    st.markdown(f"<h1 style='text-align: center;'>Welcome to {PAGE_CONFIG_APP_TITLE}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Please log in or register to continue.</p>", unsafe_allow_html=True)

    auth_form_container = st.container(border=True)
    with auth_form_container:
        if st.session_state.get('show_registration_form', False):
            st.subheader("Register New Account")
            with st.form("registration_form_sqlite", clear_on_submit=False): # Unique key
                reg_username = st.text_input("Username", key="reg_user_sqlite")
                reg_password = st.text_input("Password", type="password", key="reg_pass_sqlite")
                reg_confirm_password = st.text_input("Confirm Password", type="password", key="reg_confirm_pass_sqlite")
                reg_email = st.text_input("Email (Optional)", key="reg_email_sqlite")
                reg_full_name = st.text_input("Full Name (Optional)", key="reg_fname_sqlite")
                submitted_register = st.form_submit_button("Register")

                if submitted_register:
                    if not reg_username or not reg_password:
                        st.session_state.registration_message = ("error", "Username and password are required.")
                    elif reg_password != reg_confirm_password:
                        st.session_state.registration_message = ("error", "Passwords do not match.")
                    else:
                        reg_result = auth_service.create_user(
                            username=reg_username, password=reg_password,
                            email=reg_email, full_name=reg_full_name
                        )
                        if "error" in reg_result:
                            st.session_state.registration_message = ("error", reg_result["error"])
                        else:
                            st.session_state.registration_message = ("success", reg_result["message"])
                            st.session_state.show_registration_form = False
                    st.rerun()
            
            if st.button("Back to Login", key="back_to_login_btn_sqlite"):
                st.session_state.show_registration_form = False
                st.session_state.registration_message = None
                st.rerun()
            
            if st.session_state.get('registration_message'):
                msg_type, msg_text = st.session_state.registration_message
                if msg_type == "success": st.success(msg_text)
                else: st.error(msg_text)
        else:
            st.subheader("Login")
            with st.form("login_form_sqlite", clear_on_submit=False): # Unique key
                username = st.text_input("Username", key="login_user_sqlite", value="testuser")
                password = st.text_input("Password", type="password", key="login_pass_sqlite", value="testpassword123")
                submitted_login = st.form_submit_button("Login")

                if submitted_login:
                    user_data = auth_service.authenticate_user(username, password)
                    if user_data:
                        st.session_state.authenticated = True
                        st.session_state.username = user_data.get("username", username)
                        st.session_state.login_error = None
                        st.session_state.registration_message = None
                        logger.info(f"User '{st.session_state.username}' logged in successfully.")
                        st.rerun()
                    else:
                        st.session_state.login_error = "Invalid username or password."
                        logger.warning(f"Login failed for username: {username}")
                        st.rerun()
            
            if st.session_state.get('login_error'):
                st.error(st.session_state.login_error)
            
            if st.button("Create an Account", key="go_to_register_btn_sqlite"):
                st.session_state.show_registration_form = True
                st.session_state.login_error = None
                st.rerun()
        st.markdown("---")
        st.caption("User data is stored in a local SQLite database for this demonstration.")


# --- MAIN APPLICATION LOGIC ---
if not st.session_state.get('authenticated', False):
    show_auth_ui()
    st.stop()

# --- AUTHENTICATED APPLICATION CONTENT STARTS HERE ---
# (The rest of your app.py logic for data upload, sidebar, KPI calculation, etc. remains largely the same)
# ... (previous authenticated app content from your app.py) ...

# Logo display logic
LOGO_PATH_SIDEBAR = "assets/Trading_Mastery_Hub_600x600.png"
logo_to_display_path = LOGO_PATH_SIDEBAR
logo_base64 = None
if os.path.exists(LOGO_PATH_SIDEBAR):
    try:
        with open(LOGO_PATH_SIDEBAR, "rb") as image_file:
            logo_base64 = base64.b64encode(image_file.read()).decode()
        logo_to_display_for_st_logo = f"data:image/png;base64,{logo_base64}"
    except Exception as e:
        logger.error(f"Error encoding logo: {e}", exc_info=True)
        logo_to_display_for_st_logo = LOGO_PATH_SIDEBAR
else:
    logger.error(f"Logo file NOT FOUND at {LOGO_PATH_SIDEBAR}")
    logo_to_display_for_st_logo = None

if logo_to_display_for_st_logo:
    try:
        st.logo(logo_to_display_for_st_logo, icon_image=logo_to_display_for_st_logo)
    except Exception as e:
        logger.error(f"Error setting st.logo: {e}", exc_info=True)
        if logo_base64:
             st.sidebar.image(f"data:image/png;base64,{logo_base64}", use_column_width='auto')
        elif os.path.exists(LOGO_PATH_SIDEBAR):
             st.sidebar.image(LOGO_PATH_SIDEBAR, use_column_width='auto')


st.sidebar.header(APP_TITLE)
st.sidebar.markdown(f"Welcome, **{st.session_state.get('username', 'User')}**!")
st.sidebar.markdown("---")

theme_toggle_value = st.session_state.current_theme == "light"
toggle_label = "Switch to Dark Mode" if st.session_state.current_theme == "light" else "Switch to Light Mode"
if st.sidebar.button(toggle_label, key="theme_toggle_button_main_app_v4"): # Incremented key
    st.session_state.current_theme = "dark" if st.session_state.current_theme == "light" else "light"
    st.rerun()
st.sidebar.markdown("---")

if st.sidebar.button("Logout", key="logout_button_main_app_v3"): # Incremented key
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.login_error = None
    st.session_state.registration_message = None
    logger.info(f"User logged out.")
    st.rerun()
st.sidebar.markdown("---")

uploaded_file = st.sidebar.file_uploader(
    "Upload Trading Journal (CSV)",
    type=["csv"],
    key="app_wide_file_uploader_authed_v4" # Incremented key
)

sidebar_manager = SidebarManager(st.session_state.get('processed_data'))
current_sidebar_filters = sidebar_manager.render_sidebar_controls()
st.session_state.sidebar_filters = current_sidebar_filters

if current_sidebar_filters:
    rfr_from_sidebar = current_sidebar_filters.get('risk_free_rate', RISK_FREE_RATE)
    if st.session_state.risk_free_rate != rfr_from_sidebar:
        st.session_state.risk_free_rate = rfr_from_sidebar
        st.session_state.kpi_results = None
        logger.info(f"Risk-free rate updated via sidebar to: {rfr_from_sidebar:.4f}")

    benchmark_ticker_from_sidebar = current_sidebar_filters.get('selected_benchmark_ticker', "")
    if st.session_state.selected_benchmark_ticker != benchmark_ticker_from_sidebar:
        st.session_state.selected_benchmark_ticker = benchmark_ticker_from_sidebar
        st.session_state.selected_benchmark_display_name = next((n for n, t in AVAILABLE_BENCHMARKS.items() if t == benchmark_ticker_from_sidebar), "None")
        st.session_state.benchmark_daily_returns = None
        st.session_state.kpi_results = None
        logger.info(f"Benchmark ticker updated via sidebar to: {benchmark_ticker_from_sidebar}")

    initial_capital_from_sidebar = current_sidebar_filters.get('initial_capital', 100000.0)
    if st.session_state.initial_capital != initial_capital_from_sidebar:
        st.session_state.initial_capital = initial_capital_from_sidebar
        st.session_state.kpi_results = None
        logger.info(f"Initial capital updated via sidebar to: {initial_capital_from_sidebar:.2f}")


@log_execution_time
def get_and_process_data_with_profiling(file_obj, mapping, name):
    return data_service.get_processed_trading_data(file_obj, user_column_mapping=mapping, original_file_name=name)

if uploaded_file is not None:
    current_file_id_for_mapping = f"{uploaded_file.name}-{uploaded_file.size}-{uploaded_file.type}-mapping_stage"
    if st.session_state.last_uploaded_file_for_mapping_id != current_file_id_for_mapping:
        logger.info(f"New file '{uploaded_file.name}' for mapping. Resetting relevant session states.")
        for key_to_reset in ['column_mapping_confirmed', 'user_column_mapping', 'processed_data', 'filtered_data', 'kpi_results', 'kpi_confidence_intervals', 'benchmark_daily_returns', 'max_drawdown_period_details']:
            st.session_state[key_to_reset] = None
        
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.last_uploaded_file_for_mapping_id = current_file_id_for_mapping
        
        try:
            st.session_state.uploaded_file_bytes_for_mapper = BytesIO(uploaded_file.getvalue())
            st.session_state.uploaded_file_bytes_for_mapper.seek(0)
            df_peek = pd.read_csv(BytesIO(st.session_state.uploaded_file_bytes_for_mapper.getvalue()), nrows=5)
            st.session_state.csv_headers_for_mapping = df_peek.columns.tolist()
            st.session_state.uploaded_file_bytes_for_mapper.seek(0)
        except Exception as e_header:
            logger.error(f"Could not read CSV headers/preview from '{uploaded_file.name}': {e_header}", exc_info=True)
            display_custom_message(f"Error reading from '{uploaded_file.name}': {e_header}. Please ensure it's a valid CSV file.", "error")
            st.session_state.csv_headers_for_mapping = None
            st.session_state.uploaded_file_bytes_for_mapper = None
            st.stop()

    if st.session_state.csv_headers_for_mapping and not st.session_state.column_mapping_confirmed:
        st.session_state.processed_data = None
        st.session_state.filtered_data = None
        
        column_mapper = ColumnMapperUI(
            uploaded_file_name=st.session_state.uploaded_file_name,
            uploaded_file_bytes=st.session_state.uploaded_file_bytes_for_mapper,
            csv_headers=st.session_state.csv_headers_for_mapping,
            conceptual_columns_map=CONCEPTUAL_COLUMNS,
            conceptual_column_types=CONCEPTUAL_COLUMN_TYPES,
            conceptual_column_synonyms=CONCEPTUAL_COLUMN_SYNONYMS,
            critical_conceptual_cols=CRITICAL_CONCEPTUAL_COLUMNS,
            conceptual_column_categories=CONCEPTUAL_COLUMN_CATEGORIES
        )
        user_mapping_result = column_mapper.render()

        if user_mapping_result is not None:
            st.session_state.user_column_mapping = user_mapping_result
            st.session_state.column_mapping_confirmed = True
            st.rerun()
        else:
            st.stop() 

    if st.session_state.column_mapping_confirmed and st.session_state.user_column_mapping:
        current_file_id_proc = f"{st.session_state.uploaded_file_name}-{uploaded_file.size}-{uploaded_file.type}-processing"
        
        if st.session_state.last_processed_file_id != current_file_id_proc or st.session_state.processed_data is None:
            with st.spinner(f"Processing '{st.session_state.uploaded_file_name}'..."):
                file_obj_for_service = st.session_state.uploaded_file_bytes_for_mapper
                if file_obj_for_service:
                    file_obj_for_service.seek(0)
                    st.session_state.processed_data = get_and_process_data_with_profiling(
                        file_obj_for_service, st.session_state.user_column_mapping, st.session_state.uploaded_file_name
                    )
                else:
                    temp_bytes_re_read = BytesIO(uploaded_file.getvalue())
                    st.session_state.processed_data = get_and_process_data_with_profiling(
                        temp_bytes_re_read, st.session_state.user_column_mapping, st.session_state.uploaded_file_name
                    )

            st.session_state.last_processed_file_id = current_file_id_proc
            for key_to_reset in ['kpi_results', 'kpi_confidence_intervals', 'benchmark_daily_returns', 'max_drawdown_period_details', 'filtered_data']:
                st.session_state[key_to_reset] = None
            st.session_state.filtered_data = st.session_state.processed_data

            if st.session_state.processed_data is not None and not st.session_state.processed_data.empty:
                display_custom_message(f"Successfully processed '{st.session_state.uploaded_file_name}'. You can now navigate to analysis pages.", "success", icon="✅")
            elif st.session_state.processed_data is not None and st.session_state.processed_data.empty:
                display_custom_message(f"Processing of '{st.session_state.uploaded_file_name}' resulted in an empty dataset.", "warning")
            else:
                display_custom_message(f"Failed to process '{st.session_state.uploaded_file_name}'. Check logs and mapping.", "error")
                st.session_state.column_mapping_confirmed = False
                st.session_state.user_column_mapping = None

elif st.session_state.get('uploaded_file_name') and uploaded_file is None:
    if st.session_state.processed_data is not None:
        logger.info("File uploader is now empty. Resetting all data-dependent session states.")
        keys_to_reset_on_file_removal = [
            'processed_data', 'filtered_data', 'kpi_results', 'kpi_confidence_intervals',
            'uploaded_file_name', 'uploaded_file_bytes_for_mapper', 'last_processed_file_id',
            'user_column_mapping', 'column_mapping_confirmed', 'csv_headers_for_mapping',
            'last_uploaded_file_for_mapping_id', 'last_applied_filters', 
            'benchmark_daily_returns', 'last_fetched_benchmark_ticker',
            'last_benchmark_data_filter_shape', 'last_kpi_calc_state_id',
            'max_drawdown_period_details'
        ]
        for key_to_reset in keys_to_reset_on_file_removal:
            if key_to_reset in default_session_state:
                 st.session_state[key_to_reset] = default_session_state[key_to_reset]
            else:
                 st.session_state[key_to_reset] = None
        st.rerun()

@log_execution_time
def filter_data_with_profiling(df, filters, col_map):
    return data_service.filter_data(df, filters, col_map)

if st.session_state.processed_data is not None and not st.session_state.processed_data.empty and st.session_state.sidebar_filters:
    if st.session_state.filtered_data is None or st.session_state.last_applied_filters != st.session_state.sidebar_filters:
        with st.spinner("Applying filters to data..."):
            st.session_state.filtered_data = filter_data_with_profiling(
                st.session_state.processed_data, st.session_state.sidebar_filters, EXPECTED_COLUMNS
            )
        st.session_state.last_applied_filters = st.session_state.sidebar_filters.copy()
        for key_to_reset in ['kpi_results', 'kpi_confidence_intervals', 'benchmark_daily_returns', 'max_drawdown_period_details']:
            st.session_state[key_to_reset] = None
        logger.info("Data filtered. KPI and benchmark data will be re-calculated if needed.")

if st.session_state.filtered_data is not None and not st.session_state.filtered_data.empty:
    selected_ticker = st.session_state.get('selected_benchmark_ticker')
    if selected_ticker and selected_ticker != "" and selected_ticker.upper() != "NONE":
        refetch_benchmark = False
        if st.session_state.benchmark_daily_returns is None: refetch_benchmark = True
        elif st.session_state.last_fetched_benchmark_ticker != selected_ticker: refetch_benchmark = True
        elif st.session_state.last_benchmark_data_filter_shape != st.session_state.filtered_data.shape: refetch_benchmark = True

        if refetch_benchmark:
            date_col_conceptual = EXPECTED_COLUMNS.get('date', 'date')
            min_d_str_to_fetch, max_d_str_to_fetch = None, None
            if date_col_conceptual in st.session_state.filtered_data.columns:
                dates_for_bm_filtered = pd.to_datetime(st.session_state.filtered_data[date_col_conceptual], errors='coerce').dropna()
                if not dates_for_bm_filtered.empty:
                    min_d_filtered, max_d_filtered = dates_for_bm_filtered.min(), dates_for_bm_filtered.max()
                    if pd.notna(min_d_filtered) and pd.notna(max_d_filtered) and (max_d_filtered.date() - min_d_filtered.date()).days >= 0:
                        min_d_str_to_fetch, max_d_str_to_fetch = min_d_filtered.strftime('%Y-%m-%d'), max_d_filtered.strftime('%Y-%m-%d')
            
            if min_d_str_to_fetch and max_d_str_to_fetch:
                with st.spinner(f"Fetching benchmark data for {selected_ticker}..."):
                    st.session_state.benchmark_daily_returns = get_benchmark_data_static(selected_ticker, min_d_str_to_fetch, max_d_str_to_fetch)
                st.session_state.last_fetched_benchmark_ticker = selected_ticker
                st.session_state.last_benchmark_data_filter_shape = st.session_state.filtered_data.shape
                if st.session_state.benchmark_daily_returns is None or st.session_state.benchmark_daily_returns.empty:
                    display_custom_message(f"Could not fetch benchmark data for {selected_ticker}.", "warning")
            else:
                logger.warning(f"Cannot fetch benchmark for {selected_ticker} due to invalid date range.")
                st.session_state.benchmark_daily_returns = None
            st.session_state.kpi_results = None
    elif st.session_state.benchmark_daily_returns is not None:
        st.session_state.benchmark_daily_returns = None
        st.session_state.kpi_results = None

@log_execution_time
def get_core_kpis_with_profiling(df, rfr, benchmark_returns, capital):
    return analysis_service_instance.get_core_kpis(df, rfr, benchmark_returns, capital)

@log_execution_time
def get_advanced_drawdown_analysis_with_profiling(equity_series):
    return analysis_service_instance.get_advanced_drawdown_analysis(equity_series)

if st.session_state.filtered_data is not None and not st.session_state.filtered_data.empty:
    current_kpi_state_id_parts = [
        st.session_state.filtered_data.shape, 
        st.session_state.risk_free_rate,
        st.session_state.initial_capital,
        st.session_state.selected_benchmark_ticker
    ]
    if st.session_state.benchmark_daily_returns is not None and not st.session_state.benchmark_daily_returns.empty:
        try:
            benchmark_hash = pd.util.hash_pandas_object(st.session_state.benchmark_daily_returns.sort_index(), index=True).sum()
            current_kpi_state_id_parts.append(benchmark_hash)
        except Exception as e_hash:
            logger.warning(f"Hashing benchmark data failed: {e_hash}. Using shape as fallback.")
            current_kpi_state_id_parts.append(st.session_state.benchmark_daily_returns.shape)
    else:
        current_kpi_state_id_parts.append(None)
    current_kpi_state_id = tuple(current_kpi_state_id_parts)

    if st.session_state.kpi_results is None or st.session_state.last_kpi_calc_state_id != current_kpi_state_id:
        logger.info("Recalculating KPIs, CIs, and Max Drawdown...")
        with st.spinner("Calculating performance metrics..."):
            kpi_res = get_core_kpis_with_profiling(
                st.session_state.filtered_data,
                st.session_state.risk_free_rate,
                st.session_state.benchmark_daily_returns,
                st.session_state.initial_capital
            )
            if kpi_res and 'error' not in kpi_res:
                st.session_state.kpi_results = kpi_res
                st.session_state.last_kpi_calc_state_id = current_kpi_state_id

                date_col_dd = EXPECTED_COLUMNS.get('date')
                cum_pnl_col_dd = 'cumulative_pnl'
                equity_series_for_dd = pd.Series(dtype=float)
                if date_col_dd and cum_pnl_col_dd and date_col_dd in st.session_state.filtered_data.columns and cum_pnl_col_dd in st.session_state.filtered_data.columns:
                    temp_df_for_equity = st.session_state.filtered_data[[date_col_dd, cum_pnl_col_dd]].copy()
                    temp_df_for_equity[date_col_dd] = pd.to_datetime(temp_df_for_equity[date_col_dd], errors='coerce')
                    temp_df_for_equity.dropna(subset=[date_col_dd], inplace=True)
                    if not temp_df_for_equity.empty:
                        equity_series_for_dd = temp_df_for_equity.set_index(date_col_dd)[cum_pnl_col_dd].sort_index().dropna()
                
                if not equity_series_for_dd.empty and len(equity_series_for_dd) >= 5:
                    adv_dd_results = get_advanced_drawdown_analysis_with_profiling(equity_series_for_dd)
                    st.session_state.max_drawdown_period_details = adv_dd_results.get('max_drawdown_details') if adv_dd_results and 'error' not in adv_dd_results else None
                    if adv_dd_results and 'error' in adv_dd_results: logger.warning(f"Advanced drawdown error: {adv_dd_results['error']}")
                else:
                    st.session_state.max_drawdown_period_details = None
                    logger.info(f"Skipping advanced drawdown: not enough equity series data ({len(equity_series_for_dd)}).")

                pnl_col_for_ci = EXPECTED_COLUMNS.get('pnl')
                if pnl_col_for_ci and pnl_col_for_ci in st.session_state.filtered_data.columns:
                    pnl_series_for_ci = st.session_state.filtered_data[pnl_col_for_ci].dropna()
                    if len(pnl_series_for_ci) >= 10:
                        ci_res = analysis_service_instance.get_bootstrapped_kpi_cis(st.session_state.filtered_data, ['avg_trade_pnl', 'win_rate', 'sharpe_ratio'])
                        st.session_state.kpi_confidence_intervals = ci_res if ci_res and 'error' not in ci_res else {}
                    else:
                        st.session_state.kpi_confidence_intervals = {}
                        logger.info(f"Skipping KPI CIs: not enough PnL data ({len(pnl_series_for_ci)}).")
                else:
                    st.session_state.kpi_confidence_intervals = {}
                    logger.warning(f"PnL column ('{pnl_col_for_ci}') not found for CI calculation.")
            else:
                error_msg = kpi_res.get('error', 'Unknown error') if kpi_res else 'KPI calculation failed'
                display_custom_message(f"KPI calculation error: {error_msg}.", "error")
                st.session_state.kpi_results = None
                st.session_state.kpi_confidence_intervals = {}
                st.session_state.max_drawdown_period_details = None
elif st.session_state.filtered_data is not None and st.session_state.filtered_data.empty:
    if st.session_state.processed_data is not None and not st.session_state.processed_data.empty:
        display_custom_message("No data matches the current filter criteria.", "info")
    st.session_state.kpi_results = None
    st.session_state.kpi_confidence_intervals = {}
    st.session_state.max_drawdown_period_details = None

def main_page_layout():
    st.markdown("<div class='welcome-container'>", unsafe_allow_html=True)
    st.markdown("<div class='hero-section'>", unsafe_allow_html=True)
    st.markdown("<h1 class='welcome-title'>Trading Dashboard</h1>", unsafe_allow_html=True)
    st.markdown(f"<p class='welcome-subtitle'>Powered by {PAGE_CONFIG_APP_TITLE}</p>", unsafe_allow_html=True)
    st.markdown("<p class='tagline'>Unlock insights from your trading data with powerful analytics and visualizations.</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<h2 class='features-title' style='text-align: center; color: var(--secondary-color);'>Get Started</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,1,1], gap="large")
    with col1: st.markdown("<div class='feature-item'><h4>📄 Upload Data</h4><p>Begin by uploading your trade journal (CSV) via the sidebar.</p></div>", unsafe_allow_html=True)
    with col2: st.markdown("<div class='feature-item'><h4>📊 Analyze Performance</h4><p>Dive deep into metrics and visualizations once data is processed.</p></div>", unsafe_allow_html=True)
    with col3: st.markdown("<div class='feature-item'><h4>💡 Discover Insights</h4><p>Leverage advanced tools and AI suggestions in the dashboard pages.</p></div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div style='text-align: center; margin-top: 30px;'>", unsafe_allow_html=True)
    user_guide_page_path = "pages/0_❓_User_Guide.py"
    if os.path.exists(user_guide_page_path):
        if st.button("📘 Read the User Guide", key="welcome_user_guide_button_v4", help="Navigate to User Guide"): # Incremented key
            st.switch_page(user_guide_page_path)
    else:
        st.markdown("<p style='text-align: center; font-style: italic;'>User guide page not found.</p>", unsafe_allow_html=True)
        logger.warning(f"User Guide page not found at: {user_guide_page_path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

if not uploaded_file and st.session_state.processed_data is None:
    main_page_layout()
    st.stop()
elif uploaded_file and st.session_state.processed_data is None and not st.session_state.column_mapping_confirmed:
    if st.session_state.csv_headers_for_mapping is None and uploaded_file:
        display_custom_message("Error reading uploaded file. Ensure valid CSV.", "error")
        st.stop()
elif st.session_state.processed_data is not None and \
     (st.session_state.filtered_data is None or st.session_state.filtered_data.empty) and \
     not (st.session_state.kpi_results and 'error' not in st.session_state.kpi_results):
    pass
elif st.session_state.processed_data is None and \
     st.session_state.get('uploaded_file_name') and \
     not st.session_state.get('column_mapping_confirmed'):
    pass

scroll_buttons_component = ScrollButtons()
scroll_buttons_component.render()

logger.info(f"App '{APP_TITLE}' run cycle finished for user '{st.session_state.get('username', 'anonymous')}'.")

