"""
Timeframe Adapter Module

This module provides infrastructure-level data preprocessing for multi-timeframe
research support. It normalizes dataframe structure without modifying price values
or performing any mathematical transformations.

IMPORTANT: This is a preprocessing layer only.
- NO price value modifications
- NO resampling
- NO mathematical transformations
- Only structure cleaning and validation

The goal is to ensure consistent dataframe format across different timeframes
(1m, 5m, 15m, 1h, daily, weekly) before feeding into the quant pipeline.
"""

import pandas as pd
from typing import List


def normalize_timeframe_dataframe(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Normalize a dataframe for multi-timeframe research support.
    
    This function performs INFRASTRUCTURE-LEVEL preprocessing only:
    - Validates required columns exist
    - Converts Date column to datetime
    - Sorts data chronologically (ascending)
    - Removes duplicate timestamps
    - Forward-fills missing values
    - Ensures numeric dtypes for OHLC columns
    
    **CRITICAL: This function does NOT:**
    - Modify price values
    - Resample data
    - Perform any mathematical transformations
    - Apply any trading logic
    
    The timeframe parameter is for documentation/logging purposes only.
    All data cleaning is format-agnostic and applies uniformly across timeframes.
    
    Args:
        df: Input dataframe with market data
        timeframe: Timeframe identifier (e.g., "5m", "daily", "weekly")
            Used for validation and error messages only, not for transformations
    
    Returns:
        pd.DataFrame: Cleaned dataframe with guaranteed structure:
            - 'Date' column as datetime index
            - 'Open', 'High', 'Low', 'Close' as numeric columns
            - 'Volume' as numeric column
            - Sorted chronologically (ascending)
            - No duplicate timestamps
            - No missing values (forward-filled)
    
    Raises:
        ValueError: If required columns are missing
        ValueError: If dataframe is empty after cleaning
        ValueError: If Date column cannot be converted to datetime
    
    Example:
        >>> import pandas as pd
        >>> raw_df = pd.DataFrame({
        ...     'Date': ['2024-01-01', '2024-01-02', '2024-01-01'],  # duplicate
        ...     'Open': [100, 101, 100],
        ...     'High': [102, 103, 102],
        ...     'Low': [99, 100, 99],
        ...     'Close': [101, 102, 101],
        ...     'Volume': [1000, 1100, 1000]
        ... })
        >>> clean_df = normalize_timeframe_dataframe(raw_df, "daily")
        >>> len(clean_df)  # duplicate removed
        2
        >>> clean_df.index.name
        'Date'
        >>> clean_df['Close'].dtype
        dtype('float64')
    
    Notes:
        - This is a pure preprocessing function
        - No trading logic or price calculations
        - Designed to run BEFORE any quant models
        - Ensures consistent input format for EGARCH, Black-Scholes, etc.
        - Forward-fill is conservative: assumes last known value for gaps
    """
    
    # Required columns for OHLC data
    required_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    
    # Validate input dataframe
    if df is None or df.empty:
        raise ValueError(
            f"Cannot normalize empty dataframe for timeframe '{timeframe}'"
        )
    
    # Check for required columns
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(
            f"Missing required columns for timeframe '{timeframe}': {missing_columns}. "
            f"Required: {required_columns}"
        )
    
    # Create a copy to avoid modifying original
    df_clean = df.copy()
    
    # Convert Date column to datetime
    try:
        df_clean['Date'] = pd.to_datetime(df_clean['Date'])
    except Exception as e:
        raise ValueError(
            f"Failed to convert 'Date' column to datetime for timeframe '{timeframe}': {str(e)}"
        )
    
    # Sort by Date ascending (chronological order)
    df_clean = df_clean.sort_values('Date', ascending=True)
    
    # Drop duplicate timestamps (keep first occurrence)
    initial_rows = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=['Date'], keep='first')
    duplicates_removed = initial_rows - len(df_clean)
    
    if duplicates_removed > 0:
        # Silent cleanup - this is infrastructure, not business logic
        pass
    
    # Set Date as index
    df_clean = df_clean.set_index('Date')
    
    # Ensure OHLCV columns are numeric
    ohlcv_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in ohlcv_columns:
        try:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
        except Exception as e:
            raise ValueError(
                f"Failed to convert column '{col}' to numeric for timeframe '{timeframe}': {str(e)}"
            )
    
    # Forward-fill missing values (conservative approach)
    # This assumes last known value for gaps - common in financial data
    df_clean = df_clean.ffill()
    
    # Drop any remaining rows with NaN (likely at the start if no prior value)
    df_clean = df_clean.dropna()
    
    # Final validation
    if df_clean.empty:
        raise ValueError(
            f"Dataframe is empty after normalization for timeframe '{timeframe}'. "
            f"Check input data quality."
        )
    
    return df_clean


def validate_normalized_dataframe(df: pd.DataFrame, timeframe: str) -> dict:
    """
    Validate that a dataframe meets normalized structure requirements.
    
    This function checks data quality without modifying the dataframe.
    Used for debugging and quality assurance in multi-timeframe pipelines.
    
    Args:
        df: Dataframe to validate
        timeframe: Timeframe identifier for error messages
    
    Returns:
        dict: Validation report with keys:
            - 'valid': bool, True if all checks pass
            - 'row_count': int, number of rows
            - 'date_range': tuple (start_date, end_date)
            - 'has_required_columns': bool
            - 'date_is_index': bool
            - 'date_is_datetime': bool
            - 'is_sorted_ascending': bool
            - 'has_duplicates': bool
            - 'has_missing_values': bool
            - 'numeric_columns_valid': bool
            - 'issues': list of str, any problems found
    
    Example:
        >>> report = validate_normalized_dataframe(df, "5m")
        >>> if report['valid']:
        ...     print("DataFrame ready for pipeline")
        >>> else:
        ...     print(f"Issues: {report['issues']}")
    """
    
    issues = []
    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    # Check if dataframe is empty
    if df is None or df.empty:
        issues.append("Dataframe is empty")
        return {
            'valid': False,
            'row_count': 0,
            'date_range': (None, None),
            'has_required_columns': False,
            'date_is_index': False,
            'date_is_datetime': False,
            'is_sorted_ascending': False,
            'has_duplicates': False,
            'has_missing_values': False,
            'numeric_columns_valid': False,
            'issues': issues
        }
    
    # Check required columns
    has_required_columns = all(col in df.columns for col in required_columns)
    if not has_required_columns:
        missing = [col for col in required_columns if col not in df.columns]
        issues.append(f"Missing columns: {missing}")
    
    # Check if Date is index
    date_is_index = df.index.name == 'Date' or isinstance(df.index, pd.DatetimeIndex)
    if not date_is_index:
        issues.append("Date is not set as index or index is not DatetimeIndex")
    
    # Check if index is datetime
    date_is_datetime = isinstance(df.index, pd.DatetimeIndex)
    if not date_is_datetime and date_is_index:
        issues.append("Index is not DatetimeIndex")
    
    # Check if sorted ascending
    is_sorted_ascending = df.index.is_monotonic_increasing if date_is_datetime else False
    if not is_sorted_ascending:
        issues.append("Data is not sorted in ascending chronological order")
    
    # Check for duplicates
    has_duplicates = df.index.duplicated().any() if date_is_index else False
    if has_duplicates:
        issues.append("Duplicate timestamps found")
    
    # Check for missing values
    has_missing_values = df[required_columns].isnull().any().any() if has_required_columns else False
    if has_missing_values:
        issues.append("Missing values detected in OHLCV columns")
    
    # Check numeric dtypes
    numeric_columns_valid = True
    if has_required_columns:
        for col in required_columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                numeric_columns_valid = False
                issues.append(f"Column '{col}' is not numeric")
    
    # Get date range
    date_range = (None, None)
    if date_is_datetime and not df.empty:
        date_range = (df.index.min(), df.index.max())
    
    # Determine overall validity
    valid = len(issues) == 0
    
    return {
        'valid': valid,
        'row_count': len(df),
        'date_range': date_range,
        'has_required_columns': has_required_columns,
        'date_is_index': date_is_index,
        'date_is_datetime': date_is_datetime,
        'is_sorted_ascending': is_sorted_ascending,
        'has_duplicates': has_duplicates,
        'has_missing_values': has_missing_values,
        'numeric_columns_valid': numeric_columns_valid,
        'issues': issues
    }
