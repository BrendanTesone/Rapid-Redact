# Rapid Redact

A Windows desktop application for searching and redacting sensitive information in clinical PDF documents. Built for regulatory compliance and clinical trial transparency workflows.

**Built with strictly type-safe Python** - 100% mypy type checking enforced across the entire codebase for maximum reliability and maintainability.

---

## [::] Interface & System Screenshots

All system screenshots are organized in [`docs/screenshots/`](docs/screenshots/):

### [->] Main Application Interface
| PDF Viewer & Redaction Controls | Search Results & Preview | Export Options |
| :---: | :---: | :---: |
| *Coming Soon* | *Coming Soon* | *Coming Soon* |

### [->] Configuration & Settings
| Application Settings | Search Term Management | Batch Processing |
| :---: | :---: | :---: |
| *Coming Soon* | *Coming Soon* | *Coming Soon* |

---

## [::] Basic Functionality Summary

The application is organized into specialized tabs for different redaction workflows:

### 1. **Viewer Tab** - PDF Navigation & Preview
- Native PDF rendering with multi-page navigation, zoom, and real-time redaction preview

### 2. **Project Tab** - Export & Format Conversion
- Export redacted documents to Adobe or PleaseReview-ready formats for regulatory submission

### 3. **Matches Tab** - Text-Based Search & Redaction
- Pattern-based search for sensitive information with automatic redaction suggestions

### 4. **Dose Tab** - Clinical Dosage Detection
- Specialized detection of clinical dosage information and treatment schedules

### 5. **Gap Tab (Consistency Checker)** - Document Consistency Analysis
- Cross-document verification to ensure uniform redaction and detect missed content

### 6. **AI Tab** - AI-Powered CCI Detection
- LLM-powered analysis to suggest all possible Confidential Commercial Information (CCI) in 100+ page documents

### 7. **Amend Tab** - Document Amendment Transfer
- Track and transfer redactions across amended documents with changed content and version differences

---

## [::] Installation & Setup Instructions

### Development Setup

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/BrendanTesone/Rapid-Redact.git
   cd Rapid-Redact
   ```

2. **Install Dependencies with uv:**
   ```bash
   # Install uv package manager if not already installed
   # Windows: irm https://astral.sh/uv/install.ps1 | iex
   # macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh

   # Sync dependencies
   uv sync --frozen
   ```

3. **Configure LLM API Credentials:**
   
   Copy `.env.example` to `.env` and fill in your LiteLLM configuration:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your LiteLLM router endpoint and API key for AI detection features.

4. **Run the Application:**
   ```bash
   uv run python main.py
   ```

---

## [::] Developer Build & Deployment Instructions

### Prerequisites
- **Python:** 3.13+ (managed via `uv`)
- **uv Package Manager:** [Installation Guide](https://docs.astral.sh/uv/)
- **Inno Setup 7:** For installer creation (Windows only)
- **Git:** For version control

### Development Environment Setup

1. **Clone the Repository:**
   ```bash
   git clone ssh://git@ritscm.regeneron.com/gcttd/rapid-redact.git
   cd rapid-redact
   ```

2. **Install Dependencies:**
   ```bash
   uv sync --frozen
   ```

3. **Run Development Server:**
   ```bash
   uv run python main.py
   ```

### Building Production Executables

#### Option 1: Build Standalone Executable Only
```bash
build.bat
```
Output: `dist\Rapid-Redact.exe`

#### Option 2: Build Executable + Installer
```bash
build_and_install.bat
```
Outputs:
- `dist\Rapid-Redact.exe` (standalone)
- `installer_output\Rapid-Redact-0.1.0-setup.exe` (installer)

#### Option 3: Manual Build Steps
```bash
# 1. Build executable with PyInstaller
uv run python build_wrapper.py main.spec

# 2. Create installer with Inno Setup
iscc.exe installer.iss
```

### CI/CD Integration

This project is ready for CI/CD integration with your build system. The codebase has been successfully integrated into a Jenkins pipeline environment, though specific configuration details cannot be shared.

**CI/CD Capabilities:**
- Automated code quality checks (ruff, black, mypy)
- PyInstaller executable builds
- Inno Setup installer generation
- Artifact publishing to repository systems

---

