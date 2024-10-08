# demo.py
import os
import time
from datetime import datetime, timedelta
from colorama import init, Fore, Style

from edinet_tools import get_documents_for_date_range, download_documents
from utils import process_zip_directory
from analysis_tools import openai_completion

# Initialize colorama for cross-platform color support
init()


def print_header():
    print(f"{Fore.BLUE}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'EDINET API x OpenAI Analysis':^80}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'=' * 80}{Style.RESET_ALL}")


def print_progress(message):
    print(f"{Fore.CYAN}{message}{Style.RESET_ALL}")


def get_most_recent_documents(doc_type_codes):
    current_date = datetime.now().date()
    max_attempts = 7  # up to a week back

    for _ in range(max_attempts):
        print(f"{Fore.CYAN}Fetching documents for {current_date}...{Style.RESET_ALL}")
        docs = get_documents_for_date_range(current_date, current_date, doc_type_codes=doc_type_codes)

        if docs:
            print(f"{Fore.GREEN}Found {len(docs)} documents for {current_date}.{Style.RESET_ALL}")
            return docs, current_date

        print(f"{Fore.YELLOW}No documents found for {current_date}. Trying previous day.{Style.RESET_ALL}")
        current_date -= timedelta(days=1)

    print(f"{Fore.RED}No documents found in the last {max_attempts} days.{Style.RESET_ALL}")
    return [], None


def run_demo():
    print_header()

    print(
        f"\n{Fore.CYAN}Initializing EDINET API connection..."
        f"{Style.RESET_ALL}"
    )
    time.sleep(1)

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=2)
    doc_type_codes = ["180"]  # Extraordinary Reports

    docs, found_date = get_most_recent_documents(doc_type_codes)

    if not docs:
        print(f"{Fore.RED}No documents found. Exiting demo.{Style.RESET_ALL}")
        return

    download_dir = os.path.join(".", "downloads")
    download_documents(docs, download_dir)

    print(f"\n{Fore.CYAN}Analyzing first ten disclosures...{Style.RESET_ALL}")
    all_results = process_zip_directory(download_dir, doc_type_codes=doc_type_codes)

    print(f"\n{Fore.BLUE}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'EDINET Financial Disclosure Analysis':^80}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'=' * 80}{Style.RESET_ALL}\n")

    for i, disclosure_data in enumerate(all_results[:10], 1):
        company_name = disclosure_data.get("company_name_en", "Unknown Company")
        print(f"{Fore.MAGENTA}{i:02d}/{min(10, len(all_results)):02d} - {company_name}{Style.RESET_ALL}")
        print_progress("Analyzing disclosure data...")
        one_liner = openai_completion(disclosure_data)
        m_a_signal = openai_completion(disclosure_data, prompt_type='m_a_signal')

        print(f"{Fore.WHITE}{one_liner}{Style.RESET_ALL}\n")
        print(f"{Fore.RED}{m_a_signal}{Style.RESET_ALL}\n")
        print(f"{Fore.BLUE}{'-' * 80}{Style.RESET_ALL}\n")
        time.sleep(2)  # pause between entries for readability

    print(f"\n{Fore.GREEN}Analysis complete. {len(all_results)} documents processed for {found_date}.{Style.RESET_ALL}")

if __name__ == "__main__":
    run_demo()
