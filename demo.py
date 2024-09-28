# demo.py
import os
import time
from datetime import datetime, timedelta
from colorama import init, Fore, Style

from edinet_tools import get_documents_for_date_range, download_documents
from utils import process_zip_directory
from openai_analysis import openai_analyze

# Initialize colorama for cross-platform color support
init()

def print_header():
    print(f"{Fore.BLUE}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'EDINET API x OpenAI Analysis':^80}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'=' * 80}{Style.RESET_ALL}")

def print_progress(message):
    print(f"{Fore.CYAN}{message}{Style.RESET_ALL}")

def run_demo():
    print_header()

    print(f"\n{Fore.CYAN}Initializing EDINET API connection...{Style.RESET_ALL}")
    time.sleep(1)

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=5)
    doc_type_codes = ["180"]  # Extraordinary Reports

    print(f"{Fore.CYAN}Fetching documents filed between {start_date} and {end_date}.{Style.RESET_ALL}")

    docs = get_documents_for_date_range(start_date, end_date, doc_type_codes=doc_type_codes)

    download_dir = os.path.join(".", "downloads")
    download_documents(docs, download_dir)

    print(f"\n{Fore.CYAN}Processing documents...{Style.RESET_ALL}")
    all_results = process_zip_directory(download_dir, doc_type_codes=doc_type_codes)

    print(f"\n{Fore.BLUE}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'EDINET Financial Disclosure Analysis':^80}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'=' * 80}{Style.RESET_ALL}\n")

    for i, disclosure_data in enumerate(all_results[:10], 1):
        company_name = disclosure_data.get("company_name_en", "Unknown Company")
        print(f"{Fore.MAGENTA}Analysis {i:02d}/{min(10, len(all_results)):02d} - {company_name}{Style.RESET_ALL}")
        print_progress("Analyzing disclosure data...")
        one_liner = openai_analyze(disclosure_data)

        print(f"{Fore.WHITE}{one_liner}{Style.RESET_ALL}\n")
        print(f"{Fore.BLUE}{'-' * 80}{Style.RESET_ALL}\n")
        time.sleep(1)  # Pause between entries for readability

    print(f"\n{Fore.GREEN}Analysis complete. {len(all_results)} documents processed.{Style.RESET_ALL}")

if __name__ == "__main__":
    run_demo()
