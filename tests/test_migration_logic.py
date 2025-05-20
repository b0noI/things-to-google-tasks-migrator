import unittest
from unittest.mock import patch, MagicMock, call, ANY
import argparse
import os
import sys

# Add 'src' to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Import main function from the script.
from things_to_google_tasks import main as run_migration_main, load_config

class TestMigrationLogic(unittest.TestCase):

    # Helper to create a Namespace object from a dict
    def _make_namespace(self, **kwargs):
        return argparse.Namespace(**kwargs)

    @patch('src.things_to_google_tasks.ThingsReader')
    @patch('src.things_to_google_tasks.GoogleTasksClient')
    @patch('builtins.input', return_value='y') # Auto-confirm 'yes' for clean slate
    @patch('os.path.exists') # Mock os.path.exists globally for this test
    @patch('src.things_to_google_tasks.load_config') # Mock config loading
    def test_full_migration_flow_clean_slate(self, mock_load_config, mock_os_exists, mock_input, MockGoogleTasksClient, MockThingsReader):
        # --- Setup Mocks ---
        mock_things_reader = MockThingsReader.return_value
        mock_google_tasks_client = MockGoogleTasksClient.return_value

        # os.path.exists should return True for db_path and creds_path, False for config_file if not used
        def os_exists_side_effect(path):
            if path in ['dummy_db.sqlite', 'dummy_creds.json']:
                return True
            return False # Default for other paths like config file if not specified
        mock_os_exists.side_effect = os_exists_side_effect
        
        # Mock config loading to return empty if not used, or specific values if config_file is tested
        mock_load_config.return_value = {}


        # --- Mock Data from ThingsReader ---
        mock_things_reader.get_areas.return_value = [{'uuid': 'area1', 'title': 'Work Area From Things'}]
        mock_things_reader.get_projects.return_value = [
            {'uuid': 'proj1', 'title': 'Office Reno', 'area_uuid': 'area1', 'notes': 'Project notes', 'status': 'incomplete', 'dueDate': None}
        ]
        mock_things_reader.get_headings_for_project.return_value = [
            {'uuid': 'head1', 'title': 'Planning'}
        ]
        mock_things_reader.get_tasks_for_heading.return_value = [ # Tasks under 'Planning' heading
            {'uuid': 'taskH1', 'title': 'Call contractor', 'notes': 'Get quotes', 'status': 'incomplete', 'due_date': '2024-08-15'}
        ]
        mock_things_reader.get_tasks_for_project.return_value = [ # Tasks directly under 'Office Reno' project
            {'uuid': 'taskP1', 'title': 'Order paint', 'notes': 'Blue color', 'status': 'incomplete', 'due_date': None}
        ]
        # For standalone tasks. Ensure no overlap with project tasks for clarity.
        mock_things_reader.get_tasks.return_value = [
            {'uuid': 'taskS1', 'title': 'Buy milk', 'area_uuid': None, 'project_uuid': None, 'heading_uuid': None, 'notes': '', 'status': 'incomplete', 'due_date': None},
            # This task is part of a project, get_tasks() in things_reader would return it,
            # but the migration script filters it out from standalone processing
            # because it has a project_uuid or its uuid is in migrated_project_task_ids.
            # To test standalone, ensure it's truly standalone.
            {'uuid': 'taskH1', 'title': 'Call contractor', 'area_uuid': 'area1', 'project_uuid': 'proj1', 'heading_uuid': 'head1', 'notes': 'Get quotes', 'status': 'incomplete', 'due_date': '2024-08-15'},
            {'uuid': 'taskP1', 'title': 'Order paint', 'area_uuid': 'area1', 'project_uuid': 'proj1', 'heading_uuid': None, 'notes': 'Blue color', 'status': 'incomplete', 'due_date': None}
        ]


        # --- Mock GoogleTasksClient Behavior ---
        # Simulate no existing lists initially for clean_slate
        mock_google_tasks_client.get_task_list_by_title.return_value = None 
        
        # Return values for created lists
        mock_work_list = {'id': 'glist_work', 'title': 'Work Area From Things'}
        mock_default_list = {'id': 'glist_default', 'title': 'Things Imported Tasks'}
        
        def create_task_list_side_effect(title):
            if title == 'Work Area From Things':
                return mock_work_list
            elif title == 'Things Imported Tasks':
                return mock_default_list
            return {'id': f'glist_{title.lower()}', 'title': title}
        mock_google_tasks_client.create_task_list.side_effect = create_task_list_side_effect
        
        # Return values for created tasks (main project task, heading, tasks under heading, tasks under project, standalone)
        g_project_main_task = {'id': 'g_proj1_main', 'title': 'Office Reno'}
        g_heading_task = {'id': 'g_head1_placeholder', 'title': '--- Planning ---'}
        g_task_under_heading = {'id': 'g_taskH1', 'title': 'Call contractor'}
        g_task_under_project = {'id': 'g_taskP1', 'title': 'Order paint'}
        g_standalone_task = {'id': 'g_taskS1', 'title': 'Buy milk'}

        create_task_calls = []
        def create_task_side_effect(task_list_id, title, notes=None, due_date_str=None, parent_task_id=None):
            create_task_calls.append(call(task_list_id=task_list_id, title=title, notes=notes, due_date_str=due_date_str, parent_task_id=parent_task_id))
            if title == 'Office Reno': return g_project_main_task
            if title == '--- Planning ---': return g_heading_task
            if title == 'Call contractor': return g_task_under_heading
            if title == 'Order paint': return g_task_under_project
            if title == 'Buy milk': return g_standalone_task
            return {'id': f'g_{title.replace(" ", "").lower()}', 'title': title} # Generic fallback
        mock_google_tasks_client.create_task.side_effect = create_task_side_effect


        # --- Simulate running the main script ---
        test_args = self._make_namespace(
            db_path='dummy_db.sqlite', 
            creds_path='dummy_creds.json', 
            clean_slate=True,
            config_file=None # Explicitly not using a config file for this test run
        )
        with patch('argparse.ArgumentParser.parse_args', return_value=test_args):
            run_migration_main()

        # --- Assertions ---
        mock_input.assert_called_once_with("Are you sure you want to delete ALL Google Tasks data? This cannot be undone. [y/N]: ")
        mock_google_tasks_client.clear_all_task_lists_and_tasks.assert_called_once()

        # Area migration
        mock_google_tasks_client.create_task_list.assert_any_call(title='Work Area From Things')
        
        # Project migration (Office Reno)
        # 1. Main project task
        expected_project_call = call(
            task_list_id=mock_work_list['id'], 
            title='Office Reno', 
            notes='Project notes', 
            due_date_str=None, # from mocked project data
            parent_task_id=None
        )
        self.assertIn(expected_project_call, create_task_calls)
        
        # 2. Heading under project
        expected_heading_call = call(
            task_list_id=mock_work_list['id'], 
            title='--- Planning ---', 
            notes=None, # Headings typically don't have notes in this migration
            due_date_str=None,
            parent_task_id=g_project_main_task['id']
        )
        self.assertIn(expected_heading_call, create_task_calls)

        # 3. Task under heading
        expected_task_under_heading_call = call(
            task_list_id=mock_work_list['id'], 
            title='Call contractor', 
            notes='Get quotes', 
            due_date_str='2024-08-15',
            parent_task_id=g_heading_task['id']
        )
        self.assertIn(expected_task_under_heading_call, create_task_calls)

        # 4. Task directly under project
        expected_task_under_project_call = call(
            task_list_id=mock_work_list['id'], 
            title='Order paint', 
            notes='Blue color', 
            due_date_str=None,
            parent_task_id=g_project_main_task['id']
        )
        self.assertIn(expected_task_under_project_call, create_task_calls)
        
        # Standalone task migration ('Buy milk')
        # It should go to the default list because it has no area.
        mock_google_tasks_client.create_task_list.assert_any_call(title='Things Imported Tasks')
        expected_standalone_task_call = call(
            task_list_id=mock_default_list['id'], 
            title='Buy milk', 
            notes='', 
            due_date_str=None,
            parent_task_id=None
        )
        self.assertIn(expected_standalone_task_call, create_task_calls)

        # Verify ThingsReader close was called
        mock_things_reader.close.assert_called_once()


    @patch('src.things_to_google_tasks.ThingsReader')
    @patch('src.things_to_google_tasks.GoogleTasksClient')
    @patch('os.path.exists')
    @patch('src.things_to_google_tasks.load_config')
    def test_migration_no_clean_slate_uses_existing_lists(self, mock_load_config, mock_os_exists, MockGoogleTasksClient, MockThingsReader):
        mock_things_reader = MockThingsReader.return_value
        mock_google_tasks_client = MockGoogleTasksClient.return_value
        mock_os_exists.return_value = True # db and creds paths exist
        mock_load_config.return_value = {}

        # ThingsReader data
        mock_things_reader.get_areas.return_value = [{'uuid': 'area1', 'title': 'Personal'}]
        mock_things_reader.get_projects.return_value = [] # No projects for simplicity
        mock_things_reader.get_tasks.return_value = [
             {'uuid': 'taskS1', 'title': 'Gym session', 'area_uuid': 'area1', 'project_uuid': None, 'heading_uuid': None, 'notes': '', 'status': 'incomplete', 'due_date': None}
        ]

        # GoogleTasksClient - simulate 'Personal' list already exists
        existing_personal_list = {'id': 'glist_personal_existing', 'title': 'Personal'}
        mock_google_tasks_client.get_task_list_by_title.return_value = existing_personal_list
        
        # Task creation mock
        mock_google_tasks_client.create_task.return_value = {'id': 'gtask_gym', 'title': 'Gym session'}

        test_args = self._make_namespace(db_path='d.db', creds_path='c.json', clean_slate=False, config_file=None)
        with patch('argparse.ArgumentParser.parse_args', return_value=test_args):
            run_migration_main()

        mock_google_tasks_client.clear_all_task_lists_and_tasks.assert_not_called()
        mock_google_tasks_client.create_task_list.assert_not_called() # Should use existing
        mock_google_tasks_client.get_task_list_by_title.assert_called_with('Personal')
        
        mock_google_tasks_client.create_task.assert_called_once_with(
            task_list_id=existing_personal_list['id'],
            title='Gym session',
            notes='',
            due_date_str=None, # from mock task data
            parent_task_id=None
        )
        mock_things_reader.close.assert_called_once()


    @patch('src.things_to_google_tasks.ThingsReader')
    @patch('src.things_to_google_tasks.GoogleTasksClient')
    @patch('builtins.input', return_value='n') # User says NO to clean slate
    @patch('os.path.exists', return_value=True)
    @patch('src.things_to_google_tasks.load_config')
    def test_clean_slate_cancelled_by_user(self, mock_load_config, mock_os_exists, mock_input, MockGoogleTasksClient, MockThingsReader):
        mock_load_config.return_value = {}
        mock_google_tasks_client = MockGoogleTasksClient.return_value
        mock_things_reader = MockThingsReader.return_value

        test_args = self._make_namespace(db_path='d.db', creds_path='c.json', clean_slate=True, config_file=None)
        with patch('argparse.ArgumentParser.parse_args', return_value=test_args), \
             patch('sys.exit') as mock_sys_exit: # Patch sys.exit to prevent test runner from exiting
            run_migration_main()

        mock_input.assert_called_once()
        mock_google_tasks_client.clear_all_task_lists_and_tasks.assert_not_called()
        mock_sys_exit.assert_called_once_with(0) # Should exit gracefully
        mock_things_reader.close.assert_called_once() # Ensure cleanup happens even if exiting early


    @patch('src.things_to_google_tasks.ThingsReader')
    @patch('src.things_to_google_tasks.GoogleTasksClient')
    @patch('os.path.exists')
    @patch('src.things_to_google_tasks.load_config') # Patch load_config
    def test_config_file_usage(self, mock_load_config, mock_os_exists, MockGoogleTasksClient, MockThingsReader):
        # Simulate config file providing paths
        mock_load_config.return_value = {
            'THINGS_DB_PATH': 'config_db.sqlite',
            'GOOGLE_API_CREDENTIALS_PATH': 'config_creds.json'
        }
        # os.path.exists needs to be true for paths from config
        def os_exists_side_effect(path):
            return path in ['config_db.sqlite', 'config_creds.json', 'my_config.py']
        mock_os_exists.side_effect = os_exists_side_effect

        # Mock clients and their methods to prevent actual operations
        MockThingsReader.return_value.get_areas.return_value = []
        MockThingsReader.return_value.get_projects.return_value = []
        MockThingsReader.return_value.get_tasks.return_value = []
        MockGoogleTasksClient.return_value.get_task_list_by_title.return_value = None

        test_args = self._make_namespace(
            db_path=None, # No direct CLI path for db
            creds_path=None, # No direct CLI path for creds
            clean_slate=False,
            config_file='my_config.py'
        )
        with patch('argparse.ArgumentParser.parse_args', return_value=test_args):
            run_migration_main()
        
        mock_load_config.assert_called_once_with('my_config.py')
        # Verify ThingsReader and GoogleTasksClient were initialized with paths from config
        MockThingsReader.assert_called_once_with(db_path='config_db.sqlite')
        MockGoogleTasksClient.assert_called_once_with(credentials_path='config_creds.json')

    # TODO: Add tests for:
    # - Projects/Tasks with no Area (should go to default "Things Imported Tasks" list)
    # - Error handling if ThingsReader fails to initialize
    # - Error handling if GoogleTasksClient fails to initialize
    # - Error handling during API calls (e.g., create_task_list fails, create_task fails)
    # - Path validation errors (db_path or creds_path not found)


if __name__ == '__main__':
    unittest.main()
