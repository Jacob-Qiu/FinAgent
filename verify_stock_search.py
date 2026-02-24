
import sys
import os
import pandas as pd
from tools.akshare_search import akshare_search

def test_stock_search():
    print("=== Testing Stock Search Functionality ===")
    
    # Test Cases
    test_cases = [
        {"code": "NVDA", "type": "realtime", "market": "US (NVIDIA)"},
        {"code": "GOOG", "type": "realtime", "market": "US (Google)"},
        {"code": "00700", "type": "realtime", "market": "HK (Tencent)"},
        {"code": "BABA", "type": "realtime", "market": "US (Alibaba)"},
        {"code": "NVDA", "type": "history", "market": "US (NVIDIA History)", "start_date": "20240101", "end_date": "20240105"},
        {"code": "105.NVDA", "type": "history", "market": "US (NVIDIA History with Prefix)", "start_date": "20240101", "end_date": "20240105"},
    ]

    for case in test_cases:
        print(f"\nSearching for {case['market']} - {case['code']}...")
        try:
            if 'start_date' in case:
                result = akshare_search(case['code'], case['type'], start_date=case['start_date'], end_date=case['end_date'])
            else:
                result = akshare_search(case['code'], case['type'])

            if isinstance(result, pd.DataFrame):
                if not result.empty:
                    print(f"✅ Success! Found {len(result)} record(s).")
                    print(result.iloc[0])
                else:
                    print("❌ Failed: Empty DataFrame returned.")
            else:
                print(f"✅ Success! Result: {result}")
        except Exception as e:
            print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    # Add project root to path so imports work
    sys.path.append(os.getcwd())
    test_stock_search()
