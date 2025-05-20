import os
import peewee
from datetime import datetime

# --- Database Setup ---
# This global 'db' object will be initialized by the ThingsReader instance
# with the specific SQLite database path provided at runtime.
# This allows the models (TMArea, TMTask) to be defined globally but connect
# to the correct database when ThingsReader is instantiated.
db = peewee.SqliteDatabase(None)

class BaseModel(peewee.Model):
    """Base model class for Peewee, specifying the database instance to use."""
    class Meta:
        database = db

class TMArea(BaseModel):
    """Represents an Area in Things 3. Areas are top-level organizational units."""
    uuid = peewee.CharField(primary_key=True, help_text="Unique identifier for the area.")
    title = peewee.CharField(null=True, help_text="Title of the area.")
    trashed = peewee.IntegerField(default=0, help_text="Boolean flag (0 or 1) indicating if the area is trashed.") 

    class Meta:
        table_name = 'TMArea' # Maps to the TMTask table in Things.db

class TMTask(BaseModel):
    """
    Represents a Task, Project, or Heading in Things 3.
    The 'type' field distinguishes between them.
    """
    uuid = peewee.CharField(primary_key=True, help_text="Unique identifier for the item.")
    type = peewee.IntegerField(choices=[(0, 'Task'), (1, 'Project'), (2, 'Heading')], help_text="Type of the item: 0 for Task, 1 for Project, 2 for Heading.")
    title = peewee.CharField(null=True, help_text="Title of the item.")
    notes = peewee.TextField(null=True, help_text="Notes associated with the item.")
    
    # Foreign keys for relationships
    area = peewee.ForeignKeyField(TMArea, backref='tasks', column_name='area', null=True, help_text="Foreign key to the TMArea this item belongs to.")
    project = peewee.ForeignKeyField('self', backref='tasks_in_project', column_name='project', null=True, help_text="Foreign key to the TMTask (Project) this item belongs to (if it's a task or heading within a project).")
    heading = peewee.ForeignKeyField('self', backref='tasks_under_heading', column_name='heading', null=True, help_text="Foreign key to the TMTask (Heading) this task belongs to (if it's a task under a heading).")
    
    status = peewee.CharField(null=True, help_text="Status of the task, e.g., 'incomplete', 'completed', 'canceled'.")
    startDate = peewee.DateTimeField(null=True, help_text="Start date of the task (Things 'When' date).") # Original field name from Things
    dueDate = peewee.DateTimeField(null=True, help_text="Due date of the task (Things 'Deadline').") # Original field name from Things
    trashed = peewee.IntegerField(default=0, help_text="Boolean flag (0 or 1) indicating if the item is trashed.") # 0 for false, 1 for true

    # Peewee maps these database field names (startDate, dueDate) to model attributes automatically.
    # These attributes can be used directly in queries and when accessing model instances.
    # For example, `task_instance.startDate` and `task_instance.dueDate`.

    class Meta:
        table_name = 'TMTask' # Maps to the TMTask table in Things.db

class ThingsReader:
    """
    Reads data from the Things 3 SQLite database.
    Provides methods to fetch areas, projects, tasks, and headings.
    """
    def __init__(self, db_path):
        """
        Initializes the ThingsReader and connects to the Things 3 database.

        Args:
            db_path (str): The file path to the Things 3 SQLite database.
        
        Raises:
            FileNotFoundError: If the database file at db_path does not exist.
        """
        self.db_path = db_path
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        global db
        db.init(self.db_path)
        
        # Bind models to this specific database instance
        # This is important if you might connect to multiple databases or in testing
        self._models = [TMArea, TMTask]
        db.bind(self._models, bind_refs=False, bind_backrefs=False)
        
        db.connect()
        
        # Create SQL views for simplified querying of non-trashed Tasks, Projects, and Headings.
        # These views pre-filter by 'type' and 'trashed' status, making ORM queries cleaner.
        # Note: Peewee ORM queries in this class primarily use direct model queries with .where() clauses,
        # which is often more flexible than defining Peewee models for these views.
        # The views are created for potential direct SQL querying or if model-based view access was desired.
        db.execute_sql("CREATE VIEW IF NOT EXISTS TaskView AS SELECT * FROM TMTask WHERE type = 0 AND trashed = 0;")
        db.execute_sql("CREATE VIEW IF NOT EXISTS ProjectView AS SELECT * FROM TMTask WHERE type = 1 AND trashed = 0;")
        db.execute_sql("CREATE VIEW IF NOT EXISTS HeadingView AS SELECT * FROM TMTask WHERE type = 2 AND trashed = 0;")

    def close(self):
        """Closes the database connection if it's open."""
        if not db.is_closed():
            db.close()

    def get_areas(self):
        """
        Retrieves all non-trashed areas from the database.
        
        Returns:
            list: A list of dictionaries, where each dictionary represents an area
                  with 'uuid' and 'title' keys.
        """
        areas_query = TMArea.select(TMArea.uuid, TMArea.title).where(TMArea.trashed == 0)
        return [
            {"uuid": area.uuid, "title": area.title}
            for area in areas_query
        ]

    def get_projects(self):
        # Querying TMTask directly with a type filter for projects.
        # This approach is used instead of querying ProjectView via Peewee ORM models,
        # as it's generally more straightforward with existing model definitions.
        projects_query = TMTask.select(TMTask.uuid, TMTask.title, TMTask.notes, TMTask.area) \
                               .where((TMTask.type == 1) & (TMTask.trashed == 0))
        return [
            {
                "uuid": project.uuid,
                "title": project.title,
                "notes": project.notes,
                "area_uuid": project.area.uuid if project.area else None,
            }
            for project in projects_query
        ]

    def get_tasks(self):
        tasks_query = TMTask.select(
                            TMTask.uuid, TMTask.title, TMTask.notes, TMTask.status, 
                            TMTask.dueDate, TMTask.project, TMTask.area, TMTask.heading # Select relevant fields
                        ).where((TMTask.type == 0) & (TMTask.trashed == 0)) # Filter for tasks that are not trashed
        
        tasks_list = []
        for task in tasks_query:
            # Convert Peewee model instance to dictionary for consistent output format
            tasks_list.append({
                "uuid": task.uuid,
                "title": task.title,
                "notes": task.notes,
                "status": task.status,
                "due_date": task.dueDate, # Directly use the dueDate attribute from the model
                "project_uuid": task.project.uuid if task.project else None,
                "area_uuid": task.area.uuid if task.area else None,
                "heading_uuid": task.heading.uuid if task.heading else None,
            })
        return tasks_list

    def get_headings_for_project(self, project_uuid):
        """
        Retrieves all non-trashed headings associated with a specific project.

        Args:
            project_uuid (str): The UUID of the project.

        Returns:
            list: A list of dictionaries, where each dictionary represents a heading
                  with 'uuid' and 'title' keys.
        """
        headings_query = TMTask.select(TMTask.uuid, TMTask.title) \
                                 .where(
                                     (TMTask.type == 2) &  # Item is a Heading
                                     (TMTask.trashed == 0) &  # Heading is not trashed
                                     (TMTask.project == project_uuid)  # Belongs to the specified project
                                 )
        return [
            {"uuid": heading.uuid, "title": heading.title}
            for heading in headings_query
        ]

    def get_tasks_for_project(self, project_uuid):
        tasks_query = TMTask.select(
                            TMTask.uuid, TMTask.title, TMTask.notes, TMTask.status, TMTask.dueDate
                        ).where(
                            (TMTask.type == 0) &  # Item is a Task
                            (TMTask.trashed == 0) &  # Task is not trashed
                            (TMTask.project == project_uuid) &  # Belongs to the specified project
                            (TMTask.heading.is_null(True))  # Task is not under any heading (directly under project)
                        )
        return [
            {
                "uuid": task.uuid,
                "title": task.title,
                "notes": task.notes,
                "status": task.status,
                "due_date": task.dueDate,
            }
            for task in tasks_query
        ]
        
    def get_tasks_for_heading(self, heading_uuid):
        tasks_query = TMTask.select(
                            TMTask.uuid, TMTask.title, TMTask.notes, TMTask.status, TMTask.dueDate
                        ).where(
                            (TMTask.type == 0) &  # Item is a Task
                            (TMTask.trashed == 0) &  # Task is not trashed
                            (TMTask.heading == heading_uuid)  # Belongs to the specified heading
                        )
        return [
            {
                "uuid": task.uuid,
                "title": task.title,
                "notes": task.notes,
                "status": task.status,
                "due_date": task.dueDate,
            }
            for task in tasks_query
        ]

# Example Usage (primarily for local testing and demonstration)
# This block will only execute when the script is run directly (e.g., python src/things_reader.py)
if __name__ == '__main__':
    # This demonstration requires a 'config.py' file in the project root or adjacent to this script,
    # which defines THINGS_DB_PATH.
    # Example 'config.py':
    # THINGS_DB_PATH = '/Users/yourusername/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/Things Database/main.sqlite'

    print("--- ThingsReader Demonstration ---")
    try:
        # Attempt to import configuration to get the database path
        # This assumes config.py is in a location findable by Python's import system (e.g., project root if running from there)
        # For more robust path handling, one might adjust sys.path or use environment variables.
        import config 
        
        if not hasattr(config, 'THINGS_DB_PATH') or not config.THINGS_DB_PATH:
            print("Error: THINGS_DB_PATH is not defined or is empty in your config.py.")
            print("Please create or update config.py with the path to your Things 3 database.")
        else:
            print(f"Attempting to connect to Things DB at: {config.THINGS_DB_PATH}")
            reader = ThingsReader(db_path=config.THINGS_DB_PATH)
            
            print("\n--- Areas ---")
            areas = reader.get_areas()
            if areas:
                for area in areas:
                    print(f"  - {area['title']} (UUID: {area['uuid']})")
            else:
                print("  No areas found.")

            print("\n--- Projects ---")
            projects = reader.get_projects()
            if projects:
                for project in projects:
                    print(f"  - Project: {project['title']} (UUID: {project['uuid']})")
                    if project['area_uuid']:
                         # Find area title for better display (optional, adds queries)
                        area_info = next((a for a in areas if a['uuid'] == project['area_uuid']), None)
                        area_name = area_info['title'] if area_info else "N/A"
                        print(f"    Area: {area_name} (UUID: {project['area_uuid']})")
                    if project['notes']:
                        print(f"    Notes: {project['notes'][:50]}...") # Print first 50 chars of notes

                    print("    Headings:")
                    headings = reader.get_headings_for_project(project['uuid'])
                    if headings:
                        for heading in headings:
                            print(f"      - Heading: {heading['title']} (UUID: {heading['uuid']})")
                            tasks_under_heading = reader.get_tasks_for_heading(heading['uuid'])
                            for task in tasks_under_heading:
                                print(f"        * Task: {task['title']} (Due: {task.get('due_date', 'N/A')})")
                    else:
                        print("      No headings in this project.")

                    print("    Tasks (directly under project):")
                    tasks_in_project = reader.get_tasks_for_project(project['uuid'])
                    if tasks_in_project:
                        for task in tasks_in_project:
                             print(f"      * Task: {task['title']} (Due: {task.get('due_date', 'N/A')})")
                    else:
                        print("      No tasks directly under this project.")
            else:
                print("  No projects found.")

            print("\n--- All Non-Trashed Tasks (first 5) ---")
            all_tasks = reader.get_tasks()
            if all_tasks:
                for i, task in enumerate(all_tasks[:5]):
                    print(f"  - Task: {task['title']} (Project UUID: {task.get('project_uuid', 'N/A')}, Area UUID: {task.get('area_uuid', 'N/A')}, Due: {task.get('due_date', 'N/A')})")
                if len(all_tasks) > 5:
                    print(f"  ... and {len(all_tasks) - 5} more tasks.")
            else:
                print("  No tasks found.")
            
            reader.close()
            print("\nDatabase connection closed.")
            
    except FileNotFoundError as e:
        print(f"Database File Not Found Error: {e}")
        print("Ensure the THINGS_DB_PATH in your config.py is correct and the file exists.")
    except ImportError:
        print("Error: Could not import 'config'.")
        print("Please ensure a 'config.py' file exists in the correct location (e.g., project root)")
        print("and contains the THINGS_DB_PATH variable pointing to your Things 3 database.")
    except peewee.OperationalError as e:
        print(f"Peewee Operational Error: {e}")
        print("This might be due to an incorrect database file, a locked database (Things app might be running), or corrupted data.")
    except Exception as e:
        print(f"An unexpected error occurred during the demonstration: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- ThingsReader Demonstration Finished ---")
