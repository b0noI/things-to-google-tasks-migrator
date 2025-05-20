# Things to Google Tasks Migrator

This script migrates your tasks and projects from Things 3 (macOS application) to Google Tasks. It reads data directly from the Things 3 SQLite database and uses the Google Tasks API to create corresponding task lists, tasks, and subtasks.

## Features

*   Migrates Things Areas to new Google Task Lists.
*   Migrates Things Projects to Google Tasks (as main tasks within their respective Area's list).
*   Migrates tasks within Things Projects (including those under Headings) as subtasks in Google Tasks.
*   Things Headings are represented as placeholder subtasks under their project task in Google Tasks, with actual tasks under that heading becoming subtasks of the placeholder.
*   Option to perform a "clean slate" migration by deleting all pre-existing Google Tasks data (task lists and tasks) before starting.
*   Flexible configuration via command-line arguments or a `config.py` file.
*   Includes a suite of unit tests to verify functionality.

## Prerequisites

*   Python 3.7+
*   Access to your Things 3 database file. This script is intended to be run on a macOS machine where Things 3 is installed.
*   A Google account.

## Setup Instructions

**1. Clone the Repository:**
```bash
git clone https://github.com/your-username/things-to-google-tasks.git # Replace with actual URL
cd things-to-google-tasks
```

**2. Create a Virtual Environment (Recommended):**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

**3. Install Dependencies:**
```bash
pip install -r requirements.txt
```

**4. Set up Google API Credentials:**
*   Go to the [Google Cloud Console](https://console.cloud.google.com/).
*   Create a new project or select an existing one.
*   In the navigation menu, go to "APIs & Services" -> "Library".
*   Search for "Google Tasks API" and enable it for your project.
*   Go to "APIs & Services" -> "Credentials".
*   Click "+ CREATE CREDENTIALS" -> "OAuth client ID".
*   For "Application type", select "Desktop app".
*   Give the client ID a name (e.g., "Things Migration Script").
*   Click "Create". You will see your client ID and client secret.
*   Click "DOWNLOAD JSON" to download the client secrets file.
*   **Rename this downloaded file to `credentials.json`** and place it in the root directory of this project. Alternatively, you can specify a different path using command-line arguments or the `config.py` file.
*   **Authorization:** The first time you run the migration script, it will attempt to open a new tab in your web browser to ask you to authorize access to your Google Tasks. After successful authorization, a `token.json` file will be created in the project's root directory. This file stores your OAuth 2.0 tokens, so you won't need to re-authorize every time you run the script. Keep this file secure.

**5. Configure Things Database Path:**
*   The script needs access to your Things 3 SQLite database file. The typical path on macOS is:
    `~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/Things Database/main.sqlite`
*   You can provide this path to the script in one of two ways:
    *   **Via `config.py` (Recommended):**
        Copy the template file:
        ```bash
        cp config.py.template config.py
        ```
        Edit `config.py` and set the `THINGS_DB_PATH` variable to the correct path of your `main.sqlite` file.
        You can also set `GOOGLE_API_CREDENTIALS_PATH` in this file if your credentials JSON is not named `credentials.json` or is not in the project root.
    *   **Via Command-Line Argument:**
        Use the `--db-path` argument when running the script (see below).

## Running the Migration Script

Ensure your virtual environment is activated if you created one.

**Using `config.py` (Recommended):**
1.  Make sure you have created `config.py` from `config.py.template` and correctly set `THINGS_DB_PATH` (and `GOOGLE_API_CREDENTIALS_PATH` if needed).
2.  Run the script:
    ```bash
    python src/things_to_google_tasks.py --config-file config.py
    ```

**Using Command-Line Arguments:**
```bash
python src/things_to_google_tasks.py --db-path "/Users/yourusername/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/Things Database/main.sqlite" --creds-path "credentials.json"
```
(Replace paths with your actual paths.)

**Clean Slate Option:**
To delete all existing Google Task Lists and Tasks from your Google account before migrating your Things data, use the `--clean-slate` flag. **Warning: This is irreversible.**
```bash
python src/things_to_google_tasks.py --config-file config.py --clean-slate
```
Or with direct arguments:
```bash
python src/things_to_google_tasks.py --db-path "/path/to/your/main.sqlite" --creds-path "credentials.json" --clean-slate
```
You will be prompted for confirmation before any data is deleted.

## Running Unit Tests

To run the included unit tests to ensure the script's components are working correctly:
```bash
python -m unittest discover -s tests -p "test_*.py"
```
This command should be run from the root directory of the project.

## Project Structure

*   `src/`: Contains the main Python source code.
    *   `things_reader.py`: Handles reading data from the Things 3 database.
    *   `google_tasks_client.py`: Manages interactions with the Google Tasks API, including authentication.
    *   `things_to_google_tasks.py`: The main executable script that orchestrates the migration.
*   `tests/`: Contains unit tests for the modules in `src/`.
    *   `test_things_reader.py`
    *   `test_google_tasks_client.py`
    *   `test_migration_logic.py`
*   `requirements.txt`: Lists the Python dependencies required for the project.
*   `config.py.template`: A template for the configuration file. Copy this to `config.py` to set your database path and (optionally) credentials path.
*   `credentials.json`: (You create this) Your Google API OAuth 2.0 client secrets.
*   `token.json`: (Created after first run) Stores your Google API OAuth 2.0 access and refresh tokens.
*   `README.md`: This file.

## Troubleshooting/Notes

*   **Database Lock:** It's recommended to close the Things 3 application before running the migration script. This helps prevent potential issues with database locking, which might cause the script to fail to read the Things data.
*   **Google Tasks API Limits:** The Google Tasks API has usage limits (e.g., rate limits on requests). For users with extremely large Things databases (many thousands of tasks and projects), the script might take a significant amount of time to complete or could potentially hit these limits. Currently, the script does not support batching or advanced rate limit handling beyond what the Google client libraries provide.
*   **First Run Authorization:** Remember that on the first run, your web browser will open to ask for permission to access your Google Tasks. You need to grant this permission for the script to work.
*   **Standalone Tasks:** Tasks in Things that are not part of any project will be migrated to a Google Task List corresponding to their Area. If a standalone task has no Area, it will be placed in a default list named "Things Imported Tasks".
*   **Idempotency:**
    *   Creating Google Task Lists for Areas is idempotent (it checks for existing lists by title).
    *   Task migration is *not* fully idempotent. Running the script multiple times without the `--clean-slate` option will likely result in duplicate tasks being created in Google Tasks. If you need to re-run the migration, using `--clean-slate` is recommended for a fresh start.

---

Please replace `<repository_url>` and `https://github.com/your-username/things-to-google-tasks.git` with the actual URL of your repository if you plan to host it.
