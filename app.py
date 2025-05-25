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

# --- MODIFICATION START: st.set_page_config() moved to the top ---
from config import APP_TITLE as PAGE_CONFIG_APP_TITLE
LOGO_PATH_FOR_BROWSER_TAB = "assets/Trading_Mastery_Hub_600x600.png" # Ensure this path is correct

st.set_page_config(
    page_title=PAGE_CONFIG_APP_TITLE,
    page_icon=LOGO_PATH_FOR_BROWSER_TAB,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/trade39/Trading-Dashboard-Advance-Test-5.4', # Replace with your repo
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
    logging.basicConfig(level=logging.ERROR) # Basic logging for this critical error
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
    from services.auth_service import AuthService # <<< NEW: Import AuthService
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
    from kpi_definitions import KPI_CONFIG # Assuming this is correctly placed
except ImportError as e:
    # Fallback for critical config if import fails
    st.error(f"Fatal Error: Could not import configuration (config.py or kpi_definitions.py). App cannot start. Details: {e}")
    APP_TITLE = "TradingAppError"; LOG_FILE = "logs/error_app.log"; LOG_LEVEL = "ERROR"; LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    RISK_FREE_RATE = 0.02; CONCEPTUAL_COLUMNS = {"date": "Date", "pnl": "PnL"}; CRITICAL_CONCEPTUAL_COLUMNS = ["date", "pnl"]
    CONCEPTUAL_COLUMN_TYPES = {}; CONCEPTUAL_COLUMN_SYNONYMS = {}; KPI_CONFIG = {}; CONCEPTUAL_COLUMN_CATEGORIES = {}
    EXPECTED_COLUMNS = {"date": "date", "pnl": "pnl"}; DEFAULT_BENCHMARK_TICKER = "SPY"; AVAILABLE_BENCHMARKS = {}
    st.stop()

# Initialize logger (must be done after config variables are potentially available)
logger = setup_logger(
    logger_name=APP_TITLE, log_file=LOG_FILE, level=LOG_LEVEL, log_format=LOG_FORMAT
)
logger.info(f"Application '{APP_TITLE}' starting. Logger initialized.")

# --- Initialize Authentication Service ---
auth_service = AuthService()

# --- Theme Management ---
if 'current_theme' not in st.session_state:
    st.session_state.current_theme = "dark" # Default to dark theme
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
    css_file_path = "style.css" # Assuming style.css is in the root
    if os.path.exists(css_file_path):
        load_css(css_file_path)
    else:
        logger.error(f"style.css not found at '{css_file_path}'. Custom styles may not be applied.")
except Exception as e:
    logger.error(f"Failed to load style.css: {e}", exc_info=True)


# --- Initialize Session State (more added for auth) ---
default_session_state = {
    'app_initialized': True, 'processed_data': None, 'filtered_data': None,
    'kpi_results': None, 'kpi_confidence_intervals': {},
    'risk_free_rate': RISK_FREE_RATE, 'uploaded_file_name': None,
    'uploaded_file_bytes_for_mapper': None, 'last_processed_file_id': None,
    'user_column_mapping': None, 'column_mapping_confirmed': False,
    'csv_headers_for_mapping': None, 'last_uploaded_file_for_mapping_id': None,
    'last_applied_filters': None, 'sidebar_filters': None, 'active_tab': "📈 Overview", # Default tab for multi-page app
    'selected_benchmark_ticker': DEFAULT_BENCHMARK_TICKER,
    'selected_benchmark_display_name': next((n for n, t in AVAILABLE_BENCHMARKS.items() if t == DEFAULT_BENCHMARK_TICKER), "None"),
    'benchmark_daily_returns': None, 'initial_capital': 100000.0,
    'last_fetched_benchmark_ticker': None, 'last_benchmark_data_filter_shape': None,
    'last_kpi_calc_state_id': None,
    'max_drawdown_period_details': None,
    # --- NEW Authentication states ---
    'authenticated': False,
    'username': None,
    'login_error': None,
    'registration_message': None,
    'show_registration_form': False # To toggle between login and registration
}
for key, value in default_session_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Instantiate other services
data_service = DataService()
analysis_service_instance = AnalysisService()


# --- LOGIN / REGISTRATION UI FUNCTION ---
def show_auth_ui():
    """Displays the login and registration forms."""
    st.markdown(f"<h1 style='text-align: center;'>Welcome to {PAGE_CONFIG_APP_TITLE}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Please log in or register to continue.</p>", unsafe_allow_html=True)

    auth_form_container = st.container(border=True)

    with auth_form_container:
        if st.session_state.get('show_registration_form', False):
            st.subheader("Register New Account")
            with st.form("registration_form", clear_on_submit=False):
                reg_username = st.text_input("Username", key="reg_user")
                reg_password = st.text_input("Password", type="password", key="reg_pass")
                reg_confirm_password = st.text_input("Confirm Password", type="password", key="reg_confirm_pass")
                reg_email = st.text_input("Email (Optional)", key="reg_email")
                submitted_register = st.form_submit_button("Register")

                if submitted_register:
                    if not reg_username or not reg_password:
                        st.session_state.registration_message = ("error", "Username and password are required.")
                    elif reg_password != reg_confirm_password:
                        st.session_state.registration_message = ("error", "Passwords do not match.")
                    else:
                        reg_result = auth_service.create_user(reg_username, reg_password, email=reg_email)
                        if "error" in reg_result:
                            st.session_state.registration_message = ("error", reg_result["error"])
                        else:
                            st.session_state.registration_message = ("success", reg_result["message"])
                            st.session_state.show_registration_form = False # Switch back to login
                    st.rerun()


            if st.button("Back to Login", key="back_to_login_btn"):
                st.session_state.show_registration_form = False
                st.session_state.registration_message = None # Clear any registration messages
                st.rerun()
            
            if st.session_state.get('registration_message'):
                msg_type, msg_text = st.session_state.registration_message
                if msg_type == "success": st.success(msg_text)
                else: st.error(msg_text)


        else: # Show Login Form
            st.subheader("Login")
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("Username", key="login_user", value="testuser") # Pre-fill for convenience
                password = st.text_input("Password", type="password", key="login_pass", value="testpassword123") # Pre-fill
                submitted_login = st.form_submit_button("Login")

                if submitted_login:
                    user = auth_service.authenticate_user(username, password)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.username = user.get("username", username)
                        st.session_state.login_error = None
                        st.session_state.registration_message = None # Clear any reg messages
                        logger.info(f"User '{st.session_state.username}' logged in successfully.")
                        st.rerun()
                    else:
                        st.session_state.login_error = "Invalid username or password."
                        logger.warning(f"Login failed for username: {username}")
                        st.rerun() # Rerun to display the error

            if st.session_state.get('login_error'):
                st.error(st.session_state.login_error)
            
            if st.button("Create an Account", key="go_to_register_btn"):
                st.session_state.show_registration_form = True
                st.session_state.login_error = None # Clear any login errors
                st.rerun()
        
        st.markdown("---")
        st.caption("Note: User data is stored in-memory for this demonstration. Do not use real credentials.")

# --- MAIN APPLICATION LOGIC ---
if not st.session_state.get('authenticated', False):
    show_auth_ui()
    st.stop() # Stop execution if not authenticated

# --- AUTHENTICATED APPLICATION CONTENT STARTS HERE ---

# Logo display logic (same as before)
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
        logo_to_display_for_st_logo = LOGO_PATH_SIDEBAR # Fallback to path
else:
    logger.error(f"Logo file NOT FOUND at {LOGO_PATH_SIDEBAR}")
    logo_to_display_for_st_logo = None

if logo_to_display_for_st_logo:
    try:
        st.logo(logo_to_display_for_st_logo, icon_image=logo_to_display_for_st_logo)
    except Exception as e: # Catch potential errors if st.logo is not available or fails
        logger.error(f"Error setting st.logo: {e}", exc_info=True)
        # Fallback to st.sidebar.image if st.logo fails
        if logo_base64:
             st.sidebar.image(f"data:image/png;base64,{logo_base64}", use_column_width='auto')
        elif os.path.exists(LOGO_PATH_SIDEBAR):
             st.sidebar.image(LOGO_PATH_SIDEBAR, use_column_width='auto')


st.sidebar.header(APP_TITLE)
st.sidebar.markdown(f"Welcome, **{st.session_state.get('username', 'User')}**!") # Display username
st.sidebar.markdown("---")

# Theme toggle button
theme_toggle_value = st.session_state.current_theme == "light"
toggle_label = "Switch to Dark Mode" if st.session_state.current_theme == "light" else "Switch to Light Mode"
if st.sidebar.button(toggle_label, key="theme_toggle_button_main_app_v2"):
    st.session_state.current_theme = "dark" if st.session_state.current_theme == "light" else "light"
    st.rerun()
st.sidebar.markdown("---")

# Logout Button
if st.sidebar.button("Logout", key="logout_button_main_app"):
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.login_error = None
    st.session_state.registration_message = None
    # Optionally clear other session data related to user's session
    # for key_to_clear_on_logout in ['processed_data', 'filtered_data', 'kpi_results', ...]:
    #     if key_to_clear_on_logout in st.session_state:
    #         del st.session_state[key_to_clear_on_logout]
    logger.info(f"User logged out.")
    st.rerun()
st.sidebar.markdown("---")


# --- Data Upload and Processing Logic (Protected) ---
uploaded_file = st.sidebar.file_uploader(
    "Upload Trading Journal (CSV)",
    type=["csv"],
    key="app_wide_file_uploader_authed_v2" # Ensure key is unique if old elements linger
)

sidebar_manager = SidebarManager(st.session_state.get('processed_data'))
current_sidebar_filters = sidebar_manager.render_sidebar_controls()
st.session_state.sidebar_filters = current_sidebar_filters

# Update session state for RFR, benchmark, initial capital if changed in sidebar
if current_sidebar_filters:
    rfr_from_sidebar = current_sidebar_filters.get('risk_free_rate', RISK_FREE_RATE)
    if st.session_state.risk_free_rate != rfr_from_sidebar:
        st.session_state.risk_free_rate = rfr_from_sidebar
        st.session_state.kpi_results = None # Invalidate KPIs
        logger.info(f"Risk-free rate updated via sidebar to: {rfr_from_sidebar:.4f}")

    benchmark_ticker_from_sidebar = current_sidebar_filters.get('selected_benchmark_ticker', "")
    if st.session_state.selected_benchmark_ticker != benchmark_ticker_from_sidebar:
        st.session_state.selected_benchmark_ticker = benchmark_ticker_from_sidebar
        st.session_state.selected_benchmark_display_name = next((n for n, t in AVAILABLE_BENCHMARKS.items() if t == benchmark_ticker_from_sidebar), "None")
        st.session_state.benchmark_daily_returns = None # Invalidate benchmark data
        st.session_state.kpi_results = None # Invalidate KPIs
        logger.info(f"Benchmark ticker updated via sidebar to: {benchmark_ticker_from_sidebar}")

    initial_capital_from_sidebar = current_sidebar_filters.get('initial_capital', 100000.0)
    if st.session_state.initial_capital != initial_capital_from_sidebar:
        st.session_state.initial_capital = initial_capital_from_sidebar
        st.session_state.kpi_results = None # Invalidate KPIs
        logger.info(f"Initial capital updated via sidebar to: {initial_capital_from_sidebar:.2f}")


@log_execution_time # Decorator from common_utils
def get_and_process_data_with_profiling(file_obj, mapping, name):
    return data_service.get_processed_trading_data(file_obj, user_column_mapping=mapping, original_file_name=name)

# File processing logic (largely same as before, now within authenticated section)
if uploaded_file is not None:
    current_file_id_for_mapping = f"{uploaded_file.name}-{uploaded_file.size}-{uploaded_file.type}-mapping_stage"
    if st.session_state.last_uploaded_file_for_mapping_id != current_file_id_for_mapping:
        logger.info(f"New file '{uploaded_file.name}' for mapping. Resetting relevant session states.")
        # Reset data-dependent states
        for key_to_reset in ['column_mapping_confirmed', 'user_column_mapping', 'processed_data', 'filtered_data', 'kpi_results', 'kpi_confidence_intervals', 'benchmark_daily_returns', 'max_drawdown_period_details']:
            st.session_state[key_to_reset] = None # Or default_session_state[key_to_reset]
        
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.last_uploaded_file_for_mapping_id = current_file_id_for_mapping
        
        try:
            st.session_state.uploaded_file_bytes_for_mapper = BytesIO(uploaded_file.getvalue())
            st.session_state.uploaded_file_bytes_for_mapper.seek(0) # Ensure pointer is at the beginning
            # Peek into the CSV for headers
            df_peek = pd.read_csv(BytesIO(st.session_state.uploaded_file_bytes_for_mapper.getvalue()), nrows=5)
            st.session_state.csv_headers_for_mapping = df_peek.columns.tolist()
            st.session_state.uploaded_file_bytes_for_mapper.seek(0) # Reset pointer again for ColumnMapperUI
        except Exception as e_header:
            logger.error(f"Could not read CSV headers/preview from '{uploaded_file.name}': {e_header}", exc_info=True)
            display_custom_message(f"Error reading from '{uploaded_file.name}': {e_header}. Please ensure it's a valid CSV file.", "error")
            st.session_state.csv_headers_for_mapping = None
            st.session_state.uploaded_file_bytes_for_mapper = None
            st.stop() # Stop if headers can't be read

    # Column Mapping UI
    if st.session_state.csv_headers_for_mapping and not st.session_state.column_mapping_confirmed:
        # Ensure data states are reset before showing mapper if a new file is effectively being mapped
        st.session_state.processed_data = None
        st.session_state.filtered_data = None
        
        column_mapper = ColumnMapperUI(
            uploaded_file_name=st.session_state.uploaded_file_name,
            uploaded_file_bytes=st.session_state.uploaded_file_bytes_for_mapper, # Pass the BytesIO object
            csv_headers=st.session_state.csv_headers_for_mapping,
            conceptual_columns_map=CONCEPTUAL_COLUMNS,
            conceptual_column_types=CONCEPTUAL_COLUMN_TYPES,
            conceptual_column_synonyms=CONCEPTUAL_COLUMN_SYNONYMS,
            critical_conceptual_cols=CRITICAL_CONCEPTUAL_COLUMNS,
            conceptual_column_categories=CONCEPTUAL_COLUMN_CATEGORIES
        )
        user_mapping_result = column_mapper.render()

        if user_mapping_result is not None: # Mapping confirmed by user
            st.session_state.user_column_mapping = user_mapping_result
            st.session_state.column_mapping_confirmed = True
            st.rerun() # Rerun to proceed to data processing
        else:
            # If mapper is active but not confirmed, stop further execution on this run
            # This prevents trying to process data before mapping is done.
            st.stop() 

    # Data Processing after mapping is confirmed
    if st.session_state.column_mapping_confirmed and st.session_state.user_column_mapping:
        current_file_id_proc = f"{st.session_state.uploaded_file_name}-{uploaded_file.size}-{uploaded_file.type}-processing" # Unique ID for processing stage
        
        # Process data if it's a new file or if processed_data is None
        if st.session_state.last_processed_file_id != current_file_id_proc or st.session_state.processed_data is None:
            with st.spinner(f"Processing '{st.session_state.uploaded_file_name}'... This may take a moment."):
                file_obj_for_service = st.session_state.uploaded_file_bytes_for_mapper
                if file_obj_for_service:
                    file_obj_for_service.seek(0) # Ensure pointer is at the start for DataService
                    st.session_state.processed_data = get_and_process_data_with_profiling(
                        file_obj_for_service, st.session_state.user_column_mapping, st.session_state.uploaded_file_name
                    )
                else: # Should not happen if header reading was successful
                    logger.warning("uploaded_file_bytes_for_mapper was None at processing stage. This is unexpected.")
                    # Attempt to re-read from the original uploaded_file if it's still available (might not be robust)
                    temp_bytes_re_read = BytesIO(uploaded_file.getvalue())
                    st.session_state.processed_data = get_and_process_data_with_profiling(
                        temp_bytes_re_read, st.session_state.user_column_mapping, st.session_state.uploaded_file_name
                    )


            st.session_state.last_processed_file_id = current_file_id_proc
            # Reset downstream states as new data is processed
            for key_to_reset in ['kpi_results', 'kpi_confidence_intervals', 'benchmark_daily_returns', 'max_drawdown_period_details', 'filtered_data']:
                st.session_state[key_to_reset] = None
            st.session_state.filtered_data = st.session_state.processed_data # Initially, filtered data is all processed data

            if st.session_state.processed_data is not None and not st.session_state.processed_data.empty:
                display_custom_message(f"Successfully processed '{st.session_state.uploaded_file_name}'. You can now navigate to analysis pages.", "success", icon="✅")
            elif st.session_state.processed_data is not None and st.session_state.processed_data.empty:
                display_custom_message(f"Processing of '{st.session_state.uploaded_file_name}' resulted in an empty dataset. Please check your CSV file content and column mapping.", "warning")
                # Optionally reset mapping confirmation to allow re-mapping
                # st.session_state.column_mapping_confirmed = False
                # st.session_state.user_column_mapping = None
            else: # processed_data is None
                display_custom_message(f"Failed to process '{st.session_state.uploaded_file_name}'. Please check the logs and your column mapping. Ensure critical columns are correctly mapped and data types are appropriate.", "error")
                st.session_state.column_mapping_confirmed = False # Force re-mapping
                st.session_state.user_column_mapping = None

# Handle case where a file was uploaded, but then removed from uploader
elif st.session_state.get('uploaded_file_name') and uploaded_file is None:
    if st.session_state.processed_data is not None: # Only reset if there was data
        logger.info("File uploader is now empty. Resetting all data-dependent session states.")
        keys_to_reset_on_file_removal = [
            'processed_data', 'filtered_data', 'kpi_results', 'kpi_confidence_intervals',
            'uploaded_file_name', 'uploaded_file_bytes_for_mapper', 'last_processed_file_id',
            'user_column_mapping', 'column_mapping_confirmed', 'csv_headers_for_mapping',
            'last_uploaded_file_for_mapping_id', 'last_applied_filters', 'sidebar_filters', # Keep sidebar_filters? Or reset?
            'benchmark_daily_returns', 'last_fetched_benchmark_ticker',
            'last_benchmark_data_filter_shape', 'last_kpi_calc_state_id',
            'max_drawdown_period_details'
        ]
        for key_to_reset in keys_to_reset_on_file_removal:
            if key_to_reset in default_session_state: # Reset to initial default
                 st.session_state[key_to_reset] = default_session_state[key_to_reset]
            else: # Or just to None if not in defaults (though most should be)
                 st.session_state[key_to_reset] = None
        st.rerun() # Rerun to reflect the cleared state


# --- Data Filtering Logic (after processing) ---
@log_execution_time
def filter_data_with_profiling(df, filters, col_map):
    return data_service.filter_data(df, filters, col_map)

if st.session_state.processed_data is not None and not st.session_state.processed_data.empty and st.session_state.sidebar_filters:
    # Filter data if it's newly processed or if filters have changed
    if st.session_state.filtered_data is None or st.session_state.last_applied_filters != st.session_state.sidebar_filters:
        with st.spinner("Applying filters to data..."):
            st.session_state.filtered_data = filter_data_with_profiling(
                st.session_state.processed_data, st.session_state.sidebar_filters, EXPECTED_COLUMNS
            )
        st.session_state.last_applied_filters = st.session_state.sidebar_filters.copy() # Store a copy
        # Reset downstream states that depend on filtered_data
        for key_to_reset in ['kpi_results', 'kpi_confidence_intervals', 'benchmark_daily_returns', 'max_drawdown_period_details']:
            st.session_state[key_to_reset] = None
        logger.info("Data filtered. KPI and benchmark data will be re-calculated if needed.")


# --- Benchmark Data Fetching Logic ---
if st.session_state.filtered_data is not None and not st.session_state.filtered_data.empty:
    selected_ticker = st.session_state.get('selected_benchmark_ticker')
    if selected_ticker and selected_ticker != "" and selected_ticker.upper() != "NONE":
        refetch_benchmark = False
        if st.session_state.benchmark_daily_returns is None: refetch_benchmark = True
        elif st.session_state.last_fetched_benchmark_ticker != selected_ticker: refetch_benchmark = True
        # Check if the shape of filtered_data has changed significantly (e.g., date range changed)
        elif st.session_state.last_benchmark_data_filter_shape != st.session_state.filtered_data.shape: refetch_benchmark = True

        if refetch_benchmark:
            date_col_conceptual = EXPECTED_COLUMNS.get('date', 'date') # Get conceptual name for date
            min_d_str_to_fetch, max_d_str_to_fetch = None, None

            if date_col_conceptual in st.session_state.filtered_data.columns:
                # Ensure date column is datetime before min/max
                dates_for_bm_filtered = pd.to_datetime(st.session_state.filtered_data[date_col_conceptual], errors='coerce').dropna()
                if not dates_for_bm_filtered.empty:
                    min_d_filtered, max_d_filtered = dates_for_bm_filtered.min(), dates_for_bm_filtered.max()
                    # Ensure valid date range
                    if pd.notna(min_d_filtered) and pd.notna(max_d_filtered) and (max_d_filtered.date() - min_d_filtered.date()).days >= 0:
                        min_d_str_to_fetch, max_d_str_to_fetch = min_d_filtered.strftime('%Y-%m-%d'), max_d_filtered.strftime('%Y-%m-%d')
            
            if min_d_str_to_fetch and max_d_str_to_fetch:
                with st.spinner(f"Fetching benchmark data for {selected_ticker}..."):
                    st.session_state.benchmark_daily_returns = get_benchmark_data_static(selected_ticker, min_d_str_to_fetch, max_d_str_to_fetch)
                st.session_state.last_fetched_benchmark_ticker = selected_ticker
                st.session_state.last_benchmark_data_filter_shape = st.session_state.filtered_data.shape # Store shape after filtering
                if st.session_state.benchmark_daily_returns is None or st.session_state.benchmark_daily_returns.empty:
                    display_custom_message(f"Could not fetch benchmark data for {selected_ticker} or no data returned for the period. Ensure ticker is valid and data exists for the date range.", "warning")
            else:
                logger.warning(f"Cannot fetch benchmark for {selected_ticker} due to invalid/missing date range in filtered data.")
                st.session_state.benchmark_daily_returns = None # Ensure it's None if not fetched
            st.session_state.kpi_results = None # Invalidate KPIs as benchmark data might have changed
    elif st.session_state.benchmark_daily_returns is not None: # If benchmark was "None" or empty string
        st.session_state.benchmark_daily_returns = None
        st.session_state.kpi_results = None # Invalidate KPIs


# --- KPI Calculation Logic ---
@log_execution_time
def get_core_kpis_with_profiling(df, rfr, benchmark_returns, capital):
    return analysis_service_instance.get_core_kpis(df, rfr, benchmark_returns, capital)

@log_execution_time
def get_advanced_drawdown_analysis_with_profiling(equity_series):
    return analysis_service_instance.get_advanced_drawdown_analysis(equity_series)


if st.session_state.filtered_data is not None and not st.session_state.filtered_data.empty:
    # Create a unique ID for the current state to decide if KPIs need recalculation
    current_kpi_state_id_parts = [
        st.session_state.filtered_data.shape, # Shape of filtered data
        st.session_state.risk_free_rate,
        st.session_state.initial_capital,
        st.session_state.selected_benchmark_ticker # Active benchmark ticker
    ]
    # Add hash of benchmark returns if available
    if st.session_state.benchmark_daily_returns is not None and not st.session_state.benchmark_daily_returns.empty:
        try:
            # Sort index before hashing for consistency
            benchmark_hash = pd.util.hash_pandas_object(st.session_state.benchmark_daily_returns.sort_index(), index=True).sum()
            current_kpi_state_id_parts.append(benchmark_hash)
        except Exception as e_hash: # Handle potential errors during hashing
            logger.warning(f"Hashing benchmark data failed: {e_hash}. Using shape as fallback for KPI state.")
            current_kpi_state_id_parts.append(st.session_state.benchmark_daily_returns.shape)
    else:
        current_kpi_state_id_parts.append(None) # Placeholder if no benchmark data
    
    current_kpi_state_id = tuple(current_kpi_state_id_parts)

    if st.session_state.kpi_results is None or st.session_state.last_kpi_calc_state_id != current_kpi_state_id:
        logger.info("Recalculating KPIs, Confidence Intervals, and Max Drawdown Details due to state change...")
        with st.spinner("Calculating performance metrics... This may take a moment."):
            kpi_res = get_core_kpis_with_profiling(
                st.session_state.filtered_data,
                st.session_state.risk_free_rate,
                st.session_state.benchmark_daily_returns, # Pass the actual benchmark returns Series
                st.session_state.initial_capital
            )
            if kpi_res and 'error' not in kpi_res:
                st.session_state.kpi_results = kpi_res
                st.session_state.last_kpi_calc_state_id = current_kpi_state_id # Update last calculated state ID

                # Advanced Drawdown (relies on cumulative PnL from filtered_data)
                date_col_dd = EXPECTED_COLUMNS.get('date')
                cum_pnl_col_dd = 'cumulative_pnl' # This is an engineered column
                equity_series_for_dd = pd.Series(dtype=float)
                if date_col_dd and cum_pnl_col_dd and \
                   date_col_dd in st.session_state.filtered_data.columns and \
                   cum_pnl_col_dd in st.session_state.filtered_data.columns:
                    
                    temp_df_for_equity = st.session_state.filtered_data[[date_col_dd, cum_pnl_col_dd]].copy()
                    temp_df_for_equity[date_col_dd] = pd.to_datetime(temp_df_for_equity[date_col_dd], errors='coerce')
                    temp_df_for_equity.dropna(subset=[date_col_dd], inplace=True) # Drop rows where date conversion failed
                    
                    if not temp_df_for_equity.empty:
                        # Ensure it's sorted by date before creating the series for drawdown
                        equity_series_for_dd = temp_df_for_equity.set_index(date_col_dd)[cum_pnl_col_dd].sort_index().dropna()
                
                if not equity_series_for_dd.empty and len(equity_series_for_dd) >= 5: # Min points for meaningful DD analysis
                    adv_dd_results = get_advanced_drawdown_analysis_with_profiling(equity_series_for_dd)
                    st.session_state.max_drawdown_period_details = adv_dd_results.get('max_drawdown_details') if adv_dd_results and 'error' not in adv_dd_results else None
                    if adv_dd_results and 'error' in adv_dd_results: logger.warning(f"Advanced drawdown analysis error: {adv_dd_results['error']}")
                else:
                    st.session_state.max_drawdown_period_details = None
                    logger.info(f"Skipping advanced drawdown: not enough equity series data points ({len(equity_series_for_dd)}).")

                # Confidence Intervals (relies on PnL from filtered_data)
                pnl_col_for_ci = EXPECTED_COLUMNS.get('pnl')
                if pnl_col_for_ci and pnl_col_for_ci in st.session_state.filtered_data.columns:
                    pnl_series_for_ci = st.session_state.filtered_data[pnl_col_for_ci].dropna()
                    if len(pnl_series_for_ci) >= 10: # Min points for bootstrap
                        ci_res = analysis_service_instance.get_bootstrapped_kpi_cis(st.session_state.filtered_data, ['avg_trade_pnl', 'win_rate', 'sharpe_ratio'])
                        st.session_state.kpi_confidence_intervals = ci_res if ci_res and 'error' not in ci_res else {}
                    else:
                        st.session_state.kpi_confidence_intervals = {}
                        logger.info(f"Skipping KPI CIs: not enough PnL data points ({len(pnl_series_for_ci)}).")
                else:
                    st.session_state.kpi_confidence_intervals = {}
                    logger.warning(f"PnL column ('{pnl_col_for_ci}') not found for CI calculation.")
            else:
                error_msg = kpi_res.get('error', 'Unknown error') if kpi_res else 'KPI calculation failed'
                display_custom_message(f"KPI calculation error: {error_msg}. Please check data and mappings.", "error")
                st.session_state.kpi_results = None # Ensure it's None on error
                st.session_state.kpi_confidence_intervals = {}
                st.session_state.max_drawdown_period_details = None
elif st.session_state.filtered_data is not None and st.session_state.filtered_data.empty:
    # If filters result in empty data, clear KPIs
    if st.session_state.processed_data is not None and not st.session_state.processed_data.empty: # Only show if there was data to begin with
        display_custom_message("No data matches the current filter criteria. Adjust filters or upload a new file.", "info")
    st.session_state.kpi_results = None
    st.session_state.kpi_confidence_intervals = {}
    st.session_state.max_drawdown_period_details = None


# --- WELCOME PAGE LAYOUT FUNCTION (If no data is loaded yet) ---
def main_page_layout():
    st.markdown("<div class='welcome-container'>", unsafe_allow_html=True)
    st.markdown("<div class='hero-section'>", unsafe_allow_html=True)
    st.markdown("<h1 class='welcome-title'>Trading Dashboard</h1>", unsafe_allow_html=True)
    st.markdown(f"<p class='welcome-subtitle'>Powered by {PAGE_CONFIG_APP_TITLE}</p>", unsafe_allow_html=True)
    st.markdown("<p class='tagline'>Unlock insights from your trading data with powerful analytics and visualizations.</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<h2 class='features-title' style='text-align: center; color: var(--secondary-color);'>Get Started</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,1,1], gap="large")
    with col1:
        st.markdown("<div class='feature-item'><h4>📄 Upload Data</h4><p>Begin by uploading your trade journal (CSV) via the sidebar. Our intelligent mapping assistant will guide you.</p></div>", unsafe_allow_html=True)
    with col2:
        st.markdown("<div class='feature-item'><h4>📊 Analyze Performance</h4><p>Dive deep into comprehensive metrics and visualizations once your data is loaded and processed.</p></div>", unsafe_allow_html=True)
    with col3:
        st.markdown("<div class='feature-item'><h4>💡 Discover Insights</h4><p>Leverage advanced tools like categorical analysis and AI-driven suggestions in the dashboard pages.</p></div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div style='text-align: center; margin-top: 30px;'>", unsafe_allow_html=True)
    user_guide_page_path = "pages/0_❓_User_Guide.py" # Relative path for st.switch_page
    if os.path.exists(user_guide_page_path): # Check if the page file exists
        if st.button("📘 Read the User Guide", key="welcome_user_guide_button_v2", help="Navigate to the User Guide page"):
            st.switch_page(user_guide_page_path)
    else:
        st.markdown("<p style='text-align: center; font-style: italic;'>User guide page not found.</p>", unsafe_allow_html=True)
        logger.warning(f"User Guide page not found at expected relative path: {user_guide_page_path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# --- Page Navigation and Display Logic (Conditional on data state) ---
if not uploaded_file and st.session_state.processed_data is None:
    # This is the state before any file is uploaded or after file removal and state reset
    main_page_layout()
    st.stop() # Stop further execution if on welcome page
elif uploaded_file and st.session_state.processed_data is None and not st.session_state.column_mapping_confirmed:
    # This state means a file is in the uploader, but mapping hasn't happened or needs to happen.
    # The ColumnMapperUI logic above will handle this. If it stops (returns None), app stops.
    # If it confirms, it reruns, and this condition won't be met next time.
    if st.session_state.csv_headers_for_mapping is None and uploaded_file: # Should have been caught by header reading
        display_custom_message("Error reading the uploaded file. Please ensure it's a valid CSV and try again.", "error")
        st.stop()
    # If mapping UI is active, it will render, and this part of app.py effectively waits.
elif st.session_state.processed_data is not None and (st.session_state.filtered_data is None or st.session_state.filtered_data.empty) and not (st.session_state.kpi_results and 'error' not in st.session_state.kpi_results):
    # Data is processed, but filters might result in an empty set for display on main pages.
    # The message about "No data matches" is handled by the KPI calculation block.
    # The main app structure (sidebar, etc.) should render.
    # The individual pages will handle displaying their content or "no data" messages.
    pass # Allow app to proceed to render the selected page from sidebar
elif st.session_state.processed_data is None and st.session_state.get('uploaded_file_name') and not st.session_state.get('column_mapping_confirmed'):
    # This state can occur if a file was uploaded, mapping started but not finished, then user navigates away and back.
    # The ColumnMapperUI logic above should re-engage.
    pass


# --- Scroll Buttons Component ---
scroll_buttons_component = ScrollButtons()
scroll_buttons_component.render()

logger.info(f"App '{APP_TITLE}' run cycle finished for user '{st.session_state.get('username', 'anonymous')}'.")

