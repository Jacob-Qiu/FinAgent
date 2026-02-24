import os
import re

def rename_reports(directory):
    """
    Renames research reports in the given directory according to standardized format.
    Standard Format: [Ticker]_[CompanyName]_[Date]_[Broker]_[Subject].pdf
    """
    
    # Common brokers list for extraction
    brokers = [
        "中金公司", "中金", "东吴证券", "东吴", "华泰证券", "华泰", 
        "民生证券", "民生", "天风证券", "天风", "诚通证券", "诚通", 
        "中银国际", "中银", "慧博智能投研", "慧博", "国金证券", "国金", 
        "华源证券", "华源", "财信证券", "财信", "国信证券", "国信", 
        "华金证券", "华金", "浙商证券", "浙商", "西南证券", "西南", 
        "五矿期货", "五矿", "中邮证券", "中邮", "华西证券", "华西",
        "毕马威", "KPMG", "兴业证券", "兴业", "光大证券", "光大",
        "华创证券", "华创", "中泰证券", "中泰", "五矿证券",
        "国泰君安", "国君", "海通证券", "海通", "申万宏源", "申万",
        "招商证券", "招商", "广发证券", "广发", "安信证券", "安信",
        "银河证券", "银河", "中信建投", "建投", "中信证券", "中信",
        "方正证券", "方正", "信达证券", "信达", "开源证券", "开源",
        "东北证券", "东北", "国海证券", "国海", "太平洋",
        "华安证券", "华安", "国元证券", "国元", "东兴证券", "东兴",
        "财通证券", "财通", "德邦证券", "德邦", "西部证券", "西部",
        "万联证券", "万联", "渤海证券", "渤海", "首创证券", "首创",
        "第一创业", "一创", "川财证券", "川财", "恒泰证券", "恒泰",
        "长城证券", "长城", "爱建证券", "爱建", "国都证券", "国都",
        "宏信证券", "宏信", "万和证券", "万和", "大同证券", "大同",
        "联储证券", "联储", "中山证券", "中山", "金元证券", "金元",
        "华龙证券", "华龙", "新时代证券", "新时代", "英大证券", "英大",
        "中原证券", "中原", "世纪证券", "世纪", "国开证券", "国开",
        "红塔证券", "红塔", "华林证券", "华林", "国融证券", "国融",
        "网信证券", "网信", "大通证券", "大通", "江海证券", "江海",
        "中天证券", "中天", "国盛证券", "国盛", "中航证券", "中航",
        "联讯证券", "联讯", "东莞证券", "东莞", "华宝证券", "华宝",
        "上海证券", "上海", "长财证券", "长财", "瑞银证券", "瑞银",
        "高盛", "摩根士丹利", "摩根大通", "花旗", "汇丰", "野村",
        "大和", "麦格理", "里昂", "星展"
    ]
    
    # Sort brokers by length in descending order to match longer names first
    brokers.sort(key=len, reverse=True)

    # Compile regex for date (8 digits) and ticker (6 digits)
    date_pattern = re.compile(r"(\d{8})")
    ticker_pattern = re.compile(r"(\d{6})")

    print(f"Processing directory: {directory}")
    print(f"Target format: [Ticker]_[CompanyName]_[Date]_[Broker]_[Subject].pdf")
    
    renames = []
    
    for filename in os.listdir(directory):
        if not filename.endswith(".pdf"):
            continue
            
        # 1. Extract Date
        date_match = date_pattern.search(filename)
        date = date_match.group(1) if date_match else "00000000"
        
        # 2. Extract Ticker
        # Find all 6-digit sequences
        all_six_digits = ticker_pattern.findall(filename)
        ticker = None
        for seq in all_six_digits:
            # If this sequence is part of the extracted date (e.g. 20260128 contains 260128), skip it
            # But wait, 20260128 contains 202601, 026012, 260128. 
            # We should check if the sequence is physically inside the date string in the filename?
            # Simpler: if seq is exactly the date, ignore.
            # Even simpler: if seq is a substring of date, ignore.
            if date != "00000000" and seq in date:
                continue
            ticker = seq
            break
        
        # Determine Ticker Type (Stock, Industry, Macro)
        if not ticker:
            # Check for Macro keywords
            # Refined logic: "策略" is too broad (e.g. Industry Strategy). 
            # "经济" might be used in Industry too (e.g. Digital Economy), but usually MACRO if not specific industry.
            # Strong MACRO indicators: 宏观, 大类资产.
            is_macro = False
            if "宏观" in filename or "大类资产" in filename:
                is_macro = True
            elif "经济" in filename and "行业" not in filename:
                 # "2026年宏观经济..." -> MACRO
                 # "数字经济行业..." -> INDUSTRY
                 is_macro = True
            
            ticker = "MACRO" if is_macro else "INDUSTRY"
        
        # 3. Extract Broker
        broker = "UnknownBroker"
        for b in brokers:
            if b in filename:
                broker = b
                break
        
        # Advanced Broker Logic: If UnknownBroker, try to extract from filename structure
        # User requirement: "从原始文件名的第一个或第二个横杠（-）中间的内容提取券商名。比如 20260216-兴业证券-... ，中间的‘兴业证券’就是券商。"
        if broker == "UnknownBroker":
            # Split by hyphens only first
            hyphen_parts = filename.split('-')
            # Check if we have enough parts
            # e.g. Date-Broker-Title... -> parts[0]=Date, parts[1]=Broker
            if len(hyphen_parts) >= 2:
                # Check 2nd part (index 1)
                potential_broker = hyphen_parts[1].strip()
                # Simple validation: not empty, not too long (e.g. < 10 chars), not a digit
                if potential_broker and len(potential_broker) <= 10 and not potential_broker.isdigit():
                    broker = potential_broker
            
            # If still unknown, maybe it's in the 3rd part?
            # e.g. Date-Ticker-Broker-... (less common but possible)
            if broker == "UnknownBroker" and len(hyphen_parts) >= 3:
                 potential_broker = hyphen_parts[2].strip()
                 if potential_broker and len(potential_broker) <= 10 and not potential_broker.isdigit():
                    broker = potential_broker

        
        # 4. Extract CompanyName and Subject
        # Strategy: Remove known parts (Date, Ticker, Broker) from filename
        # Then clean and split the remaining string.
        
        clean_name = filename.replace(".pdf", "")
        if date != "00000000":
            clean_name = clean_name.replace(date, "")
        if broker != "UnknownBroker":
            clean_name = clean_name.replace(broker, "")
        if ticker and ticker.isdigit():
             clean_name = clean_name.replace(ticker, "")
             
        # Insert spaces before common report types to help splitting Subject from Company/Industry
        # e.g. "计算机行业深度报告" -> "计算机行业 深度 报告"
        # This helps extracting "计算机行业" as CompanyName
        report_keywords = ["深度", "报告", "研究", "专题", "策略", "月报", "周报", "点评", "前瞻", "趋势", "展望"]
        for kw in report_keywords:
            clean_name = clean_name.replace(kw, f" {kw} ")

        # Replace common separators with space for splitting
        # Including Chinese punctuation
        clean_name = re.sub(r"[-_ \s：:,\.（）\(\)\[\]【】]+", " ", clean_name)
        parts = clean_name.strip().split()
        
        company_name = "UnknownCompany"
        subject = "UnknownSubject"
        
        if parts:
            # Heuristic: 
            # Usually the first part is the Company/Industry/Category
            company_name = parts[0]
            
            if len(parts) > 1:
                subject = "_".join(parts[1:])
            else:
                subject = "Report"
                
            # Special case: if CompanyName is just a report keyword (unlikely due to replace logic, but possible)
            # e.g. if filename was just "深度报告", split -> "深度", "报告". Company="深度".
            # We can't fix everything perfectly without NLP.
            
            # Refinement for MACRO
            if ticker == "MACRO":
                 # If company_name is NOT "宏观" or similar, but the filename implies it.
                 # E.g. "2026年十大趋势展望" -> Parts: "2026年", "十大", "趋势", "展望"
                 # CompanyName = "2026年".
                 # If we detected MACRO, maybe we can default CompanyName to "宏观经济" if the extracted name doesn't look like a category?
                 # But "2026年" is valid as a subject start.
                 pass

        # Construct new filename
        new_filename = f"{ticker}_{company_name}_{date}_{broker}_{subject}.pdf"
        
        # Final cleanup: remove illegal characters, replace spaces with underscores
        new_filename = new_filename.replace(" ", "_")
        new_filename = re.sub(r"[^\w\-\.]", "_", new_filename) # Keep only alphanumeric, -, ., _
        new_filename = re.sub(r"_+", "_", new_filename) # Deduplicate underscores
        
        # Rename logic handles Chinese characters? \w matches them in Python 3.
        # Let's verify. Yes, re.sub with \w keeps Chinese.
        
        if filename != new_filename:
             renames.append((filename, new_filename))

    # Safety Check: Print changes

    print("\nProposed Changes:")
    print("-" * 60)
    for original, new in renames:
        print(f"Original: {original}")
        print(f"New:      {new}")
        print("-" * 60)
        
    if not renames:
        print("No files to rename.")
        return

    # Ask for confirmation
    confirm = input("\nDo you want to proceed with renaming? (y/n): ").strip().lower()
    if confirm == 'y':
        for original, new in renames:
            old_path = os.path.join(directory, original)
            new_path = os.path.join(directory, new)
            try:
                os.rename(old_path, new_path)
                print(f"Renamed: {original} -> {new}")
            except Exception as e:
                print(f"Error renaming {original}: {e}")
        print("\nRenaming complete.")
    else:
        print("\nOperation cancelled.")

if __name__ == "__main__":
    target_dir = "/Users/maowenyuan/Desktop/科技/"
    if os.path.exists(target_dir):
        rename_reports(target_dir)
    else:
        print(f"Directory not found: {target_dir}")
