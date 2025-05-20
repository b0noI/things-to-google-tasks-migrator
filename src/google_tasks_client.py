import os
import datetime

# Google API and OAuth libraries
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request # Required for token refresh
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Constants ---
# Defines the scope of access requested from the Google Tasks API.
# 'auth/tasks' allows reading and writing tasks and task lists.
SCOPES = ['https://www.googleapis.com/auth/tasks']
# Default filename for storing user's OAuth 2.0 access and refresh tokens.
TOKEN_FILE = 'token.json' 

class GoogleTasksClient:
    """
    A client for interacting with the Google Tasks API.
    Handles authentication, and provides methods for managing task lists and tasks.
    """
    def __init__(self, credentials_path="credentials.json"):
        """
        Initializes the GoogleTasksClient.

        Args:
            credentials_path (str): Path to the Google API client secrets JSON file
                                    (downloaded from Google Cloud Console). Defaults to "credentials.json".
        
        Raises:
            FileNotFoundError: If the `credentials_path` file does not exist when new authentication is required.
            googleapiclient.errors.HttpError: If building the service client fails.
        """
        self.credentials_path = credentials_path
        self.service = self._authenticate()

    def _authenticate(self):
        """
        Authenticates with the Google Tasks API using OAuth 2.0.
        -   Attempts to load existing credentials from `TOKEN_FILE`.
        -   If credentials are not found, are invalid, or expired and cannot be refreshed,
            it initiates the OAuth 2.0 authorization flow.
        -   Saves valid credentials to `TOKEN_FILE` for future use.

        Returns:
            googleapiclient.discovery.Resource: An authorized Google Tasks API service instance.
        
        Raises:
            FileNotFoundError: If `self.credentials_path` is not found during the OAuth flow.
            googleapiclient.errors.HttpError: If building the service client fails after authentication.
        """
        creds = None
        # Step 1: Try to load existing tokens from TOKEN_FILE.
        # TOKEN_FILE stores the user's access and refresh tokens, and is created
        # automatically when the authorization flow completes for the first time.
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
        # Step 2: If credentials are not loaded, or are invalid/expired, attempt to refresh or get new ones.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                # If credentials exist but are expired and have a refresh token, try to refresh them.
                try:
                    print("Credentials expired. Attempting to refresh token...")
                    creds.refresh(Request()) # Request() is from google.auth.transport.requests
                    print("Token refreshed successfully.")
                except Exception as e:
                    print(f"Error refreshing token: {e}. Need to re-authenticate.")
                    creds = None # Force re-authentication
            
            if not creds: # If refresh failed or no token.json, initiate new OAuth flow.
                print("No valid credentials found. Starting new OAuth 2.0 flow...")
                if not os.path.exists(self.credentials_path):
                    # This is a critical error: the client secrets file is needed for OAuth.
                    raise FileNotFoundError(
                        f"Credentials file not found at {self.credentials_path}. "
                        "Please download your OAuth 2.0 client secrets from Google Cloud Console, "
                        "save it (e.g., as 'credentials.json'), and provide the correct path."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                # run_local_server will open a browser window for user authorization.
                creds = flow.run_local_server(port=0)
                print("OAuth 2.0 flow completed. Credentials obtained.")
            
            # Step 3: Save the (newly obtained or refreshed) credentials for the next run.
            with open(TOKEN_FILE, 'w') as token_file_handle:
                token_file_handle.write(creds.to_json())
            print(f"Credentials saved to {TOKEN_FILE}")
        
        # Step 4: Build and return the Google Tasks API service client.
        try:
            service = build('tasks', 'v1', credentials=creds)
            print("Google Tasks API service client built successfully.")
            return service
        except HttpError as err:
            # This error can occur if the API is not enabled or other service-level issues.
            print(f"An API error occurred during service build: {err}")
            raise 

    def get_task_lists(self):
        """
        Fetches all task lists associated with the authenticated user's account.

        Returns:
            list: A list of task list objects (dictionaries), or an empty list if an error occurs or no lists exist.
        """
        try:
            results = self.service.tasklists().list().execute()
            return results.get('items', [])
        except HttpError as err:
            print(f"An API error occurred while fetching task lists: {err}")
            return []

    def get_task_list_by_title(self, title):
        """
        Finds a specific task list by its title.

        Args:
            title (str): The title of the task list to find.

        Returns:
            dict: The task list object if found, otherwise None.
        """
        task_lists = self.get_task_lists()
        for task_list in task_lists:
            if task_list['title'] == title:
                return task_list
        return None

    def create_task_list(self, title):
        """
        Creates a new task list with the given title.

        Args:
            title (str): The title for the new task list.

        Returns:
            dict: The created task list object, or None if an error occurred.
        """
        try:
            task_list_body = {'title': title}
            created_list = self.service.tasklists().insert(body=task_list_body).execute()
            print(f"Task list '{title}' created successfully (ID: {created_list['id']}).")
            return created_list
        except HttpError as err:
            print(f"An API error occurred while creating task list '{title}': {err}")
            return None

    def delete_task_list(self, task_list_id):
        """
        Deletes a task list specified by its ID.

        Args:
            task_list_id (str): The ID of the task list to delete.
        """
        try:
            self.service.tasklists().delete(tasklist=task_list_id).execute()
            print(f"Task list ID '{task_list_id}' deleted successfully.")
        except HttpError as err:
            # Specifically check for 404 if the list was already deleted or never existed
            if err.resp.status == 404:
                print(f"Task list ID '{task_list_id}' not found. Could not delete.")
            else:
                print(f"An API error occurred while deleting task list ID '{task_list_id}': {err}")


    def clear_all_task_lists_and_tasks(self):
        """
        Deletes ALL task lists and ALL tasks within them for the authenticated user.
        This is a destructive operation.
        """
        print("Clearing all task lists and tasks...")
        task_lists = self.get_task_lists()
        if not task_lists:
            print("No task lists found to delete.")
            return

        for task_list in task_lists:
            print(f"Deleting task list: {task_list.get('title', 'N/A')} (ID: {task_list['id']})")
            try:
                self.delete_task_list(task_list['id'])
            except HttpError as err:
                # Log error and continue to try deleting other lists
                print(f"Failed to delete task list {task_list['id']}: {err}")
        print("Finished clearing all task lists.")


    def create_task(self, task_list_id, title, notes=None, due_date_str=None, parent_task_id=None):
        """
        Creates a new task in a specified task list.

        Args:
            task_list_id (str): The ID of the task list where the task will be created.
            title (str): The title of the task.
            notes (str, optional): Optional notes for the task.
            due_date_str (str, optional): Due date for the task in 'YYYY-MM-DD' format.
                                       If provided, it will be converted to RFC3339 UTC timestamp
                                       (e.g., '2023-08-15T00:00:00.000Z').
            parent_task_id (str, optional): ID of the parent task if creating a subtask.

        Returns:
            dict: The created task object as returned by the API, or None if an error occurred.
        """
        task_body = {'title': title}
        if notes:
            task_body['notes'] = notes
        
        if due_date_str:
            try:
                # Convert 'YYYY-MM-DD' to RFC3339 UTC timestamp format required by Google Tasks API.
                # Example: '2023-08-15' becomes '2023-08-15T00:00:00.000Z'.
                # This assumes the due date is for the beginning of the day in UTC.
                # For tasks due "any time on a day", this is a common representation.
                dt = datetime.datetime.strptime(due_date_str, '%Y-%m-%d')
                task_body['due'] = dt.isoformat() + 'Z' 
            except ValueError:
                print(f"Warning: Invalid due date format '{due_date_str}'. Please use YYYY-MM-DD. Task will be created without a due date.")
                # Task creation proceeds without the due date if format is invalid.
                # Alternatively, one could raise an error or return None here.

        try:
            if parent_task_id:
                created_task = self.service.tasks().insert(
                    tasklist=task_list_id, 
                    body=task_body,
                    parent=parent_task_id
                ).execute()
            else:
                 created_task = self.service.tasks().insert(
                    tasklist=task_list_id, 
                    body=task_body
                ).execute()
            # print(f"Task '{title}' created in list ID '{task_list_id}'.")
            return created_task
        except HttpError as err:
            print(f"An API error occurred while creating task '{title}' in list ID '{task_list_id}': {err}")
            return None

    def get_tasks_in_list(self, task_list_id, show_completed=False, show_hidden=False):
        """
        Fetches tasks from a specified task list.

        Args:
            task_list_id (str): The ID of the task list.
            show_completed (bool): Whether to include completed tasks.
            show_hidden (bool): Whether to include hidden tasks.

        Returns:
            list: A list of task objects, or an empty list if an error occurred.
        """
        try:
            results = self.service.tasks().list(
                tasklist=task_list_id,
                showCompleted=show_completed,
                showHidden=show_hidden
            ).execute()
            return results.get('items', [])
        except HttpError as err:
            print(f"An API error occurred while fetching tasks for list ID '{task_list_id}': {err}")
            return []

# Example usage (for local testing and demonstration purposes)
# This block will only execute when the script is run directly (e.g., python src/google_tasks_client.py)
if __name__ == '__main__':
    # IMPORTANT: To run this example, you need:
    # 1. `credentials.json` from Google Cloud Console with OAuth 2.0 client ID for a Desktop App.
    #    Place this file in the same directory as this script, or provide the correct path to GoogleTasksClient.
    # 2. You will need to authorize the application when it runs for the first time. This will
    #    create a `token.json` file, storing your OAuth tokens.

    print("--- GoogleTasksClient Demonstration ---")
    try:
        # Initialize the client. Ensure 'credentials.json' is available or provide path.
        client = GoogleTasksClient(credentials_path="credentials.json") 
        print("GoogleTasksClient initialized successfully.")

        # --- Example Operations ---

        # Optional: Clear all existing task lists (use with extreme caution!)
        # confirm_clear = input("DANGER: Clear ALL task lists and tasks? (yes/NO): ")
        # if confirm_clear.lower() == 'yes':
        #     print("\n--- Clearing all task lists (if any) ---")
        #     client.clear_all_task_lists_and_tasks()
        #     print("--- Finished clearing task lists ---")
        # else:
        #     print("Skipping clear operation.")

        # 1. Fetch and display existing task lists
        print("\n--- Fetching Task Lists ---")
        task_lists = client.get_task_lists()
        if task_lists:
            print("Available Task Lists:")
            for task_list in task_lists:
                print(f"  - {task_list['title']} (ID: {task_list['id']})")
        else:
            print("No task lists found.")

        # 2. Create a new task list
        print("\n--- Creating a Test Task List ---")
        list_title = "My Test List from Script"
        # Check if list already exists to avoid duplicates in demo
        existing_list = client.get_task_list_by_title(list_title)
        if existing_list:
            print(f"Task list '{list_title}' already exists with ID: {existing_list['id']}")
            test_list = existing_list
        else:
            test_list = client.create_task_list(list_title)
        
        if test_list:
            test_list_id = test_list['id']
            print(f"Using task list '{test_list['title']}' (ID: {test_list_id}) for further tests.")

            # 3. Create tasks in the new list
            print("\n--- Creating Tasks ---")
            task1_title = "Buy groceries for the week"
            task1 = client.create_task(
                test_list_id, 
                task1_title, 
                notes="- Milk\n- Bread\n- Eggs", 
                due_date_str="2024-07-20" # Example date
            )
            if task1: print(f"  Task created: '{task1['title']}' (ID: {task1['id']})")
            
            task2_title = "Schedule dentist appointment"
            task2 = client.create_task(test_list_id, task2_title)
            if task2: print(f"  Task created: '{task2['title']}' (ID: {task2['id']})")

            # 4. Create a subtask (if task1 was created)
            if task1:
                subtask_title = "Get almond milk"
                subtask1 = client.create_task(
                    test_list_id, 
                    subtask_title, 
                    parent_task_id=task1['id']
                )
                if subtask1: print(f"  Subtask created: '{subtask1['title']}' under '{task1['title']}'")

            # 5. Get and display tasks in the test list
            print(f"\n--- Tasks in '{test_list['title']}' ---")
            tasks_in_list = client.get_tasks_in_list(test_list_id, show_completed=True, show_hidden=True)
            if tasks_in_list:
                for task in tasks_in_list:
                    print(f"  - {task['title']} (ID: {task['id']}, Status: {task.get('status', 'N/A')})")
                    if task.get('notes'):
                        print(f"    Notes: {task['notes']}")
                    if task.get('due'):
                        # Format due date for readability if it exists
                        due_datetime = datetime.datetime.fromisoformat(task['due'].replace('Z', '+00:00'))
                        print(f"    Due: {due_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    # Google Tasks API list() doesn't inherently nest subtasks.
                    # One would typically fetch all tasks and reconstruct hierarchy if needed,
                    # or make separate calls to get children of a specific task if the API supported it directly.
                    # The `parent` property on a task indicates its parent if it's a subtask.
            else:
                print("No tasks found in this list.")
            
            # Optional: Delete the test task list for cleanup
            # confirm_delete_list = input(f"\nDelete the test task list '{test_list['title']}'? (yes/NO): ")
            # if confirm_delete_list.lower() == 'yes':
            #     print(f"--- Deleting Test Task List: '{test_list['title']}' ---")
            #     client.delete_task_list(test_list_id)
            #     print("--- Test task list deleted ---")
        else:
            print(f"Could not create or retrieve '{list_title}' for testing, so further task operations skipped.")

    except FileNotFoundError as e:
        print(f"Error: {e}. Please ensure 'credentials.json' (or the path you provided) is correct and the file exists.")
    except HttpError as e:
        # Detailed error from Google API
        print(f"An HTTP error occurred: Status {e.resp.status}, Reason: {e.resp.reason}, Content: {e.content.decode()}")
    except Exception as e:
        print(f"An unexpected error occurred during the demonstration: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- GoogleTasksClient Demonstration Finished ---")
