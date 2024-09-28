# EDINET API Tools :jp:

This project provides a set of tools for interacting with Japan's [EDINET](https://disclosure2.edinet-fsa.go.jp/) (Electronic Disclosure for Investors Network) API v2, processing financial disclosure documents, and experimental tools for analyzing them using OpenAI's language models.

## Features

- 📅 Retrieve and filter disclosure documents by type and date range
- 📂 Download and process ZIP files containing CSV data effortlessly
- 🧹 Clean and process text data from financial disclosures
- 🤖 Analyze financial disclosure data using OpenAI models for deeper insights

## Requirements

- Python 3.7+
- EDINET API key
- OpenAI API key

## Installation

1. Clone this repository
2. Install required packages: `pip install -r requirements.txt`
3. Set up environment variables:
   - Create a `.env` file in the project root
   - Add your API keys:
     ```
     EDINET_API_KEY=<your_edinet_api_key>
     OPENAI_API_KEY=<your_openai_api_key>
     ```

## Usage

Run the demo script to see the tools in action:

```
python demo.py
```

This will:
- Fetch recent "Extraordinary Reports" from EDINET
- Download and process the documents
- Generate concise summaries using OpenAI's GPT-4o model

## Main Components

- `edinet_tools.py`: Functions for interacting with the EDINET API
- `utils.py`: Utility functions for file processing and text cleaning
- `openai_analysis.py`: Functions for analyzing document data using OpenAI's API
- `demo.py`: Demonstration script showing the tool's capabilities

## Customization

You can modify the `PROMPT_TEMPLATES` in `openai_analysis.py` to customize the analysis output or add new analysis instructions.

## Contributing

Please feel free to submit a Pull Request, or get in touch via email: [mahelmer28@gmail.com](mailto:mahelmer28@gmail.com)

## Disclaimer

This project is an independent tool and is not affiliated with, endorsed by, or in any way officially connected with the Financial Services Agency (FSA) of Japan or any of its subsidiaries or affiliates. The official EDINET website can be found at [https://disclosure2.edinet-fsa.go.jp/](https://disclosure2.edinet-fsa.go.jp/).

This software is provided "as is" for informational purposes only. The creator assumes no liability for errors, omissions, or any consequences of using this software. This tool does not provide financial advice. Users are solely responsible for verifying information and for any decisions made based on it. Use at your own risk.

## License

This project is licensed under the MIT License.
