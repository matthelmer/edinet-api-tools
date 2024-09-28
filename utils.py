# utils.py
import os
import pandas as pd
import re
import chardet
import tempfile
import zipfile
from typing import List, Dict


# Encoding and file reading
def detect_encoding(file_path):
    with open(file_path, 'rb') as file:
        raw_data = file.read()
    return chardet.detect(raw_data)['encoding']


def read_csv_file(file_path):
    encodings = ['utf-16', 'utf-16le', 'utf-16be']
    encodings.append(detect_encoding(file_path))
    encodings.extend(
        ['utf-8', 'iso-8859-1', 'windows-1252', 'shift-jis', 'euc-jp']
    )
    for encoding in encodings:
        try:
            df = pd.read_csv(file_path, encoding=encoding, sep='\t')
            return df
        except (UnicodeDecodeError, pd.errors.EmptyDataError):
            continue
    print(f"Failed to read {file_path}. Unable to determine correct encoding.")
    return None


# Text processing
def clean_text(text):
    # replace full-width space with regular space
    text = text.replace('\u3000', ' ')
    # remove excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # replace specific Japanese punctuation with Western equivalents
    return text.replace('　', ' ').replace('。', '. ').replace('、', ', ')


# CSV processing
def process_csv_file(file_path):
    df = read_csv_file(file_path)
    if df is None:
        return None

    result = {
        'file_name': os.path.splitext(os.path.basename(file_path))[0],
        'text_blocks': {}   # hold TextBlocks encountered
    }

    id_to_key = {
        'jpdei_cor:EDINETCodeDEI': 'edinet_code',
        'jpdei_cor:FilerNameInJapaneseDEI': 'company_name_ja',
        'jpdei_cor:FilerNameInEnglishDEI': 'company_name_en',
        'jpdei_cor:DocumentTypeDEI': 'document_type',
        'jpcrp-esr_cor:DocumentTitleCoverPage': 'document_title',
        'jpcrp-esr_cor:TitleAndNameOfRepresentativeCoverPage':
            'representative',
        'jpcrp-esr_cor:AddressOfRegisteredHeadquarterCoverPage':
            'headquarters_address',
        'jpcrp-esr_cor:TelephoneNumberCoverPage': 'phone_number',
    }

    for _, row in df.iterrows():
        element_id = row['要素ID']
        if element_id in id_to_key:
            result[id_to_key[element_id]] = clean_text(row['値'])
        elif 'TextBlock' in element_id:
            key = element_id.split(':')[-1].replace('TextBlock', '')
            result['text_blocks'][key] = clean_text(row['値'])
    return result


def process_csv_directory(directory_path):
    xbrl_to_csv_dir = os.path.join(directory_path, "XBRL_TO_CSV")
    if os.path.isdir(xbrl_to_csv_dir):
        directory_path = xbrl_to_csv_dir

    csv_files = [f for f in os.listdir(directory_path) if f.endswith('.csv')]
    results = []

    for filename in csv_files:
        file_path = os.path.join(directory_path, filename)
        result = process_csv_file(file_path)
        if result:
            results.append(result)
        else:
            print(f"Warning: No results from {filename}")
    return results


# ZIP file processing
def process_zip_file(path_to_zip_file, doc_id, doc_type_code):
    all_results = []
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(path_to_zip_file, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            results = process_csv_directory(temp_dir)
            for result in results:
                result['docID'] = doc_id
                result['doc_type_code'] = doc_type_code
            all_results.extend(results)
    except Exception as e:
        # print(f"Error processing {path_to_zip_file}: {str(e)}")
        pass
    return all_results


def process_zip_directory(directory_path: str,
                          doc_type_codes: List[str] = None) -> List[Dict]:
    all_results = []
    for filename in os.listdir(directory_path):
        if filename.endswith('.zip'):
            file_path = os.path.join(directory_path, filename)
            doc_id, doc_type_code, _ = filename.split('-', 2)
            if doc_type_codes is None or doc_type_code in doc_type_codes:
                results = process_zip_file(file_path, doc_id, doc_type_code)
                all_results.extend(results)
    return all_results
