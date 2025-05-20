import argparse
import sys
import os
import importlib.util # For dynamically loading the config.py file
from datetime import datetime # Not directly used in this file, but good practice if time elements were needed

# Import custom modules from the 'src' directory
from things_reader import ThingsReader
from google_tasks_client import GoogleTasksClient

# --- Configuration Loading ---
def load_config(config_path):
    """
    Dynamically loads configuration settings from a specified Python file.
    This allows users to store sensitive or environment-specific paths (like DB path)
    outside the main script.

    Args:
        config_path (str): The path to the Python configuration file (e.g., "config.py").

    Returns:
        dict: A dictionary containing the configuration settings found in the file (e.g.,
              {'THINGS_DB_PATH': '...', 'GOOGLE_API_CREDENTIALS_PATH': '...'}).
              Returns None if the config file is not found.
    """
    if not os.path.exists(config_path):
        print(f"Error: Config file not found at {config_path}")
        return None
    
    # Create a module specification from the file path.
    spec = importlib.util.spec_from_file_location("config_module", config_path)
    if spec is None or spec.loader is None: # Check if spec or loader is None
        print(f"Error: Could not create module spec for config file at {config_path}")
        return None
    config_module = importlib.util.module_from_spec(spec)
    # Execute the module to make its attributes available.
    spec.loader.exec_module(config_module)
    
    # Extract relevant configuration variables.
    config = {}
    if hasattr(config_module, 'THINGS_DB_PATH'):
        config['THINGS_DB_PATH'] = config_module.THINGS_DB_PATH
    if hasattr(config_module, 'GOOGLE_API_CREDENTIALS_PATH'):
        config['GOOGLE_API_CREDENTIALS_PATH'] = config_module.GOOGLE_API_CREDENTIALS_PATH
    
    return config

# --- Main Migration Logic ---
def main():
    """
    Main function to orchestrate the migration process.
    Parses arguments, loads configuration, initializes clients, and performs migration steps.
    """
    # --- Argument Parsing ---
    # Sets up command-line argument parsing for user inputs.
    parser = argparse.ArgumentParser(
        description="Migrate tasks and projects from Things 3 to Google Tasks.",
        formatter_class=argparse.RawTextHelpFormatter # For better help text formatting
    )
    parser.add_argument(
        "--db-path", 
        help="Path to your Things 3 SQLite database file (main.sqlite).\n"
             "Example: '/Users/youruser/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/Things Database/main.sqlite'"
    )
    parser.add_argument(
        "--creds-path", 
        help="Path to your Google API credentials JSON file (e.g., 'credentials.json').\n"
             "This file is obtained from Google Cloud Console for OAuth 2.0."
    )
    parser.add_argument(
        "--config-file", 
        help="Path to a Python configuration file (e.g., 'config.py') where\n"
             "THINGS_DB_PATH and GOOGLE_API_CREDENTIALS_PATH can be defined."
    )
    parser.add_argument(
        "--clean-slate", 
        action="store_true", 
        default=False,
        help="If set, ALL existing Google Task lists and tasks will be deleted\n"
             "from your Google account before the migration starts. Use with caution!"
    )
    args = parser.parse_args()

    # --- Configuration Resolution ---
    # Determine DB path and credentials path, prioritizing command-line args, then config file.
    db_path = args.db_path
    creds_path = args.creds_path

    if args.config_file:
        print(f"Attempting to load configuration from: {args.config_file}")
        if not os.path.exists(args.config_file):
            print(f"Error: Specified config file not found at {args.config_file}")
            sys.exit(1)
        config_from_file = load_config(args.config_file)
        if config_from_file:
            # If paths are not provided via CLI, use values from config file.
            db_path = db_path or config_from_file.get('THINGS_DB_PATH')
            creds_path = creds_path or config_from_file.get('GOOGLE_API_CREDENTIALS_PATH')
            print("Configuration loaded successfully.")
        else:
            # load_config would have printed an error if file exists but loading failed.
            # If load_config returned None and file exists, it means an issue within load_config.
            print(f"Failed to load or parse the config file: {args.config_file}")
            sys.exit(1)

    # --- Path Validation ---
    # Ensure necessary paths are provided and exist.
    if not db_path:
        print("Error: Things 3 database path was not provided. Please use --db-path or set THINGS_DB_PATH in your --config-file.")
        sys.exit(1)
    if not creds_path:
        print("Error: Google API credentials path was not provided. Please use --creds-path or set GOOGLE_API_CREDENTIALS_PATH in your --config-file.")
        sys.exit(1)

    if not os.path.exists(db_path):
        print(f"Error: The specified Things 3 database path does not exist: {db_path}")
        sys.exit(1)
    if not os.path.exists(creds_path):
        print(f"Error: The specified Google API credentials file does not exist: {creds_path}")
        sys.exit(1)
        
    print(f"\n--- Configuration Summary ---")
    print(f"Using Things DB from: {db_path}")
    print(f"Using Google Credentials from: {creds_path}")
    print(f"Clean slate mode: {'Enabled' if args.clean_slate else 'Disabled'}")
    print("-----------------------------\n")

    # --- Initialize API Clients ---
    # Initialize ThingsReader for database access and GoogleTasksClient for API interaction.
    try:
        things_reader = ThingsReader(db_path=db_path)
        print("ThingsReader initialized successfully.")
    except FileNotFoundError as e: # Should be caught by os.path.exists, but good for defense
        print(f"Error initializing ThingsReader (FileNotFound): {e}")
        sys.exit(1)
    except Exception as e: # Catch other potential errors from ThingsReader init (e.g., peewee operational error)
        print(f"An unexpected error occurred while initializing ThingsReader: {e}")
        sys.exit(1)

    try:
        google_tasks_client = GoogleTasksClient(credentials_path=creds_path)
        print("GoogleTasksClient initialized successfully (OAuth flow might run if first time).")
    except FileNotFoundError as e: # Should be caught by os.path.exists for creds_path
        print(f"Error initializing GoogleTasksClient (FileNotFound): {e}")
        sys.exit(1)
    except Exception as e: # Catch other errors like HttpError during service build or auth issues
        print(f"An unexpected error occurred while initializing GoogleTasksClient: {e}")
        sys.exit(1)

    # --- Clean Slate Operation ---
    # If --clean-slate is enabled, delete all existing Google Tasks data after user confirmation.
    if args.clean_slate:
        print("\nWARNING: The --clean-slate option is enabled.")
        confirm = input("This will delete ALL existing task lists and tasks from your Google Tasks account. This action CANNOT be undone. Are you absolutely sure? [y/N]: ")
        if confirm.lower() == 'y':
            print("Proceeding with deleting all Google Tasks data...")
            try:
                google_tasks_client.clear_all_task_lists_and_tasks()
                print("All Google Tasks data has been cleared.")
            except Exception as e: # Catch potential errors during the clear operation
                print(f"An error occurred during the clean slate operation: {e}")
                things_reader.close() # Ensure DB connection is closed
                sys.exit(1)
        else:
            print("Clean slate operation cancelled by the user. Exiting.")
            things_reader.close() # Ensure DB connection is closed
            sys.exit(0) # Exit gracefully
    
    # --- Migration Process ---
    print("\n--- Starting Migration: Things 3 to Google Tasks ---")
    # Cache for Google Task Lists: maps Things Area UUID to Google Task List {'id': ..., 'title': ...}
    # This avoids repeatedly fetching or creating the same Google Task List.
    google_task_lists_cache = {} 
    
    # Step 1: Migrate Things Areas to Google Task Lists
    print("\n[Step 1/3] Migrating Areas to Google Task Lists...")
    try:
        areas = things_reader.get_areas()
        if not areas:
            print("No Areas found in Things.")
        else:
            for area in areas:
                area_title = area['title']
                area_uuid = area['uuid']
                print(f"  Processing Area: '{area_title}' (UUID: {area_uuid})")
                
                existing_list = google_tasks_client.get_task_list_by_title(area_title)
                if existing_list:
                    print(f"    Found existing Google Task List: '{existing_list['title']}' (ID: {existing_list['id']})")
                    google_task_lists_cache[area_uuid] = {'id': existing_list['id'], 'title': existing_list['title']}
                else:
                    print(f"    Creating Google Task List for Area: '{area_title}'...")
                    new_list = google_tasks_client.create_task_list(title=area_title)
                    if new_list:
                        google_task_lists_cache[area_uuid] = {'id': new_list['id'], 'title': new_list['title']}
                        print(f"    Created Google Task List: '{new_list['title']}' (ID: {new_list['id']})")
                    else:
                        print(f"    Failed to create Google Task List for Area: '{area_title}'. Skipping related items.")
    except Exception as e:
        print(f"Error during Area migration: {e}")
        # Decide if to continue or exit

    # Default/Fallback Google Task List for items without an Area or if Area migration failed
    DEFAULT_LIST_TITLE = "Things Imported Tasks"  # Name for the default list for items without an Area
    default_google_list_cache = None # Cache for the default list object itself

    def get_or_create_default_list():
        """
        Retrieves or creates a default Google Task List for items that don't belong to a specific Area.
        Uses a local cache (`default_google_list_cache`) to avoid redundant API calls.

        Returns:
            dict: The default Google Task List object {'id': ..., 'title': ...}, or None if creation fails.
        """
        nonlocal default_google_list_cache # Allows modification of the outer scope variable
        if default_google_list_cache:
            return default_google_list_cache
        
        # Try to find an existing default list
        existing_default = google_tasks_client.get_task_list_by_title(DEFAULT_LIST_TITLE)
        if existing_default:
            print(f"    Found existing default Google Task List: '{existing_default['title']}' (ID: {existing_default['id']})")
            default_google_list_cache = existing_default
            return default_google_list_cache
        
        # If not found, create it
        print(f"    Default Google Task List '{DEFAULT_LIST_TITLE}' not found. Creating it...")
        created_default = google_tasks_client.create_task_list(DEFAULT_LIST_TITLE)
        if created_default:
            print(f"    Successfully created default Google Task List: '{created_default['title']}' (ID: {created_default['id']})")
            default_google_list_cache = created_default
            return default_google_list_cache
        else:
            # This is a significant issue if we can't even create a default list.
            print(f"    FATAL ERROR: Could not create the default Google Task List '{DEFAULT_LIST_TITLE}'. "
                  "Tasks without an Area may not be migrated.")
            return None # Indicates failure

    # Step 2: Migrate Things Projects and their contents (Headings and Tasks)
    print("\n[Step 2/3] Migrating Projects and their associated Headings & Tasks...")
    # Set to keep track of Things item UUIDs (tasks, headings) that have been processed as part of a project.
    # This prevents them from being processed again in the "standalone tasks" step.
    migrated_project_task_ids = set() 

    try:
        projects = things_reader.get_projects() # Fetch all non-trashed projects
        if not projects:
            print("No Projects found in Things.")
        else:
            for project in projects:
                project_title = project['title']
                project_uuid = project['uuid']
                project_notes = project.get('notes', '')
                area_uuid = project.get('area_uuid')
                
                print(f"  Processing Project: '{project_title}' (UUID: {project_uuid})")

                target_list_info = None
                if area_uuid and area_uuid in google_task_lists_cache:
                    target_list_info = google_task_lists_cache[area_uuid]
                else:
                    print(f"    Project '{project_title}' has no Area or Area not migrated. Using default list.")
                    target_list_info = get_or_create_default_list()
                    if not target_list_info:
                        print(f"    Skipping project '{project_title}' as no suitable Google Task List found/created.")
                        continue
                
                target_list_id = target_list_info['id']

                # Create the main "Project Task" in Google Tasks
                # Create the main "Project Task" in Google Tasks.
                # Things Projects are represented as main tasks in Google Tasks.
                # Their associated Things tasks and headings will become subtasks under this main task.
                project_main_task_title = f"{project_title}" # Using project title directly
                print(f"    Creating Google Task for Project '{project_title}' in list '{target_list_info['title']}'...")
                g_project_task = google_tasks_client.create_task(
                    task_list_id=target_list_id, 
                    title=project_main_task_title, 
                    notes=project_notes # Migrate project notes
                )

                if not g_project_task:
                    print(f"    ERROR: Failed to create main Google Task for Project '{project_title}'. Skipping its sub-items.")
                    continue # Move to the next Things project
                
                # Add the Things Project's UUID to the set of processed items.
                # Although Projects themselves aren't tasks in the same way in the DB, this conceptual marking helps.
                migrated_project_task_ids.add(project_uuid) 
                print(f"    Successfully created Google Task for Project: '{g_project_task['title']}' (ID: {g_project_task['id']})")

                # Migrate Headings and Tasks under those Headings for the current Project
                headings = things_reader.get_headings_for_project(project_uuid=project_uuid) # Get non-trashed headings for this project
                for heading in headings:
                    heading_title = heading['title']
                    heading_uuid = heading['uuid']
                    print(f"      Processing Heading: '{heading_title}' under Project '{project_title}'")
                    
                    # Things Headings are represented as placeholder subtasks under the main project task.
                    # Tasks that were under this Heading in Things will become subtasks of this placeholder.
                    g_heading_task_title = f"--- {heading_title} ---" # Visual cue for headings
                    g_heading_task = google_tasks_client.create_task(
                        task_list_id=target_list_id,
                        title=g_heading_task_title,
                        parent_task_id=g_project_task['id'] # Subtask to the main project task
                    )
                    if not g_heading_task:
                        print(f"      ERROR: Failed to create placeholder Google Task for Heading '{heading_title}'. Skipping its tasks.")
                        continue # Move to the next Heading
                    
                    migrated_project_task_ids.add(heading_uuid) # Mark Things Heading as processed
                    print(f"      Successfully created placeholder Google Task for Heading: '{g_heading_task['title']}' (ID: {g_heading_task['id']})")

                    # Migrate Tasks that were under this Heading in Things
                    tasks_under_heading = things_reader.get_tasks_for_heading(heading_uuid=heading_uuid)
                    for task in tasks_under_heading: # These are non-trashed tasks
                        task_title = task['title']
                        task_uuid = task['uuid']
                        print(f"        Migrating Task (under Heading '{heading_title}'): '{task_title}'")
                        g_task = google_tasks_client.create_task(
                            task_list_id=target_list_id,
                            title=task_title,
                            notes=task.get('notes', ''),
                            due_date_str=task.get('due_date'), # `get_tasks_for_heading` provides 'due_date'
                            parent_task_id=g_heading_task['id'] # Subtask to the heading's placeholder task
                        )
                        if g_task:
                            migrated_project_task_ids.add(task_uuid) # Mark Things Task as processed
                            print(f"        Successfully created Google Task: '{g_task['title']}' (ID: {g_task['id']})")
                        else:
                            print(f"        ERROR: Failed to create Google Task for: '{task_title}'")
                
                # Migrate Tasks that are directly under the Project (not under any Heading)
                project_direct_tasks = things_reader.get_tasks_for_project(project_uuid=project_uuid) # Gets non-trashed, non-heading tasks
                if project_direct_tasks:
                    print(f"      Migrating tasks directly under Project '{project_title}'...")
                for task in project_direct_tasks:
                    task_title = task['title']
                    task_uuid = task['uuid']
                    print(f"        Migrating direct Task: '{task_title}'")
                    g_task = google_tasks_client.create_task(
                        task_list_id=target_list_id,
                        title=task_title,
                        notes=task.get('notes', ''),
                        due_date_str=task.get('due_date'),
                        parent_task_id=g_project_task['id']
                    )
                    if g_task:
                        migrated_project_task_ids.add(task_uuid)
                        print(f"        Created Task: '{g_task['title']}' (ID: {g_task['id']})")
                    else:
                        print(f"        Failed to create task: '{task_title}'")

    except Exception as e:
        print(f"Error during Project migration: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging


    # Step 3: Migrate Standalone Tasks
    # These are tasks from Things that are not part of any project (i.e., project_uuid is None)
    # and have not already been processed as part of a project's structure.
    print("\n[Step 3/3] Migrating Standalone Tasks (Tasks not in any Project)...")
    try:
        all_things_tasks = things_reader.get_tasks() # Fetches all non-trashed tasks of type 0
        
        # Filter for tasks that are truly standalone:
        # - Not already processed (its UUID is not in migrated_project_task_ids)
        # - Does not have a 'project_uuid' (according to ThingsReader's get_tasks method output)
        standalone_tasks_to_migrate = [
            task for task in all_things_tasks 
            if task['uuid'] not in migrated_project_task_ids and not task.get('project_uuid')
        ]

        if not standalone_tasks_to_migrate:
            print("  No standalone tasks found to migrate.")
        else:
            print(f"  Found {len(standalone_tasks_to_migrate)} standalone tasks for migration.")
            for task in standalone_tasks_to_migrate:
                task_title = task['title']
                task_uuid = task['uuid'] # For logging/tracking, though not added to migrated_project_task_ids here
                area_uuid = task.get('area_uuid')

                print(f"    Processing Standalone Task: '{task_title}' (UUID: {task_uuid})")

                # Determine the target Google Task List for this standalone task
                target_list_info = None
                if area_uuid and area_uuid in google_task_lists_cache:
                    # If task has an Area, and that Area was migrated to a Google Task List
                    target_list_info = google_task_lists_cache[area_uuid]
                else:
                    # If no Area, or Area not found in cache, use the default list
                    if area_uuid:
                        print(f"      Task '{task_title}' belongs to Area {area_uuid}, but this Area was not found in cache. Using default list.")
                    else:
                        print(f"      Task '{task_title}' has no Area. Using default list.")
                    target_list_info = get_or_create_default_list()
                    
                    if not target_list_info:
                        print(f"      ERROR: No suitable Google Task List (Area-specific or default) found/created for standalone task '{task_title}'. Skipping.")
                        continue # Skip this task
                
                target_list_id = target_list_info['id']
                
                # Create the standalone task in the determined Google Task List
                g_task = google_tasks_client.create_task(
                    task_list_id=target_list_id,
                    title=task_title,
                    notes=task.get('notes', ''),
                    due_date_str=task.get('due_date') # `get_tasks` provides 'due_date'
                )
                if g_task:
                    print(f"      Successfully created Standalone Google Task: '{g_task['title']}' in list '{target_list_info['title']}' (ID: {g_task['id']})")
                else:
                    print(f"      ERROR: Failed to create standalone Google Task for: '{task_title}'")
    except Exception as e:
        print(f"An error occurred during Standalone Task migration: {e}")
        import traceback
        traceback.print_exc() # Print full traceback

    # --- Migration Cleanup ---
    print("\n--- Finalizing Migration ---")
    try:
        things_reader.close()
        print("Things 3 database connection closed successfully.")
    except Exception as e:
        print(f"Error closing Things 3 database connection: {e}")

    print("\nMigration process completed.")
    print("Please check your Google Tasks account to see the migrated items.")

if __name__ == "__main__":
    # This ensures that main() is called only when the script is executed directly,
    # not when it's imported as a module.
    main()
