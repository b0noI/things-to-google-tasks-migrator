import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from google_tasks_client import GoogleTasksClient, TOKEN_FILE, SCOPES
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request # For token refresh
# Assuming HttpError is from googleapiclient.errors
from googleapiclient.errors import HttpError 
from datetime import datetime

class TestGoogleTasksClient(unittest.TestCase):

    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
    @patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
    @patch('googleapiclient.discovery.build')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def setUp(self, mock_file_open_builtin, mock_os_exists, mock_build, mock_flow_from_secrets, mock_creds_from_file):
        # Store mocks for later use if needed
        self.mock_file_open_builtin = mock_file_open_builtin
        self.mock_os_exists = mock_os_exists
        self.mock_build = mock_build
        self.mock_flow_from_secrets = mock_flow_from_secrets
        self.mock_creds_from_file = mock_creds_from_file
        
        # Setup mock service
        self.mock_service = MagicMock()
        self.mock_build.return_value = self.mock_service
        
        # Mock credentials flow
        self.mock_creds = MagicMock(spec=Credentials)
        self.mock_creds.valid = True # Assume valid initially
        self.mock_creds.expired = False
        self.mock_creds.refresh_token = None # Default to no refresh token initially

        # Scenario 1: token.json exists and is valid
        self.mock_os_exists.side_effect = lambda path: path == TOKEN_FILE or path == 'dummy_creds.json'
        self.mock_creds_from_file.return_value = self.mock_creds
        
        self.client = GoogleTasksClient(credentials_path='dummy_creds.json')

    def _reset_auth_mocks(self):
        self.mock_os_exists.reset_mock()
        self.mock_creds_from_file.reset_mock()
        self.mock_flow_from_secrets.reset_mock()
        self.mock_build.reset_mock()
        self.mock_file_open_builtin.reset_mock()
        self.mock_service.reset_mock()

        # Re-patch the mock_creds object as it might have been modified by tests (e.g. .valid)
        self.mock_creds = MagicMock(spec=Credentials)
        self.mock_creds.valid = True 
        self.mock_creds.expired = False
        self.mock_creds.refresh_token = None
        self.mock_creds_from_file.return_value = self.mock_creds # For from_authorized_user_file path
        
        # For from_client_secrets_file path
        mock_flow_instance = self.mock_flow_from_secrets.return_value
        mock_flow_instance.run_local_server.return_value = self.mock_creds


    def test_authentication_token_exists_valid(self):
        self._reset_auth_mocks()
        self.mock_os_exists.side_effect = lambda path: path == TOKEN_FILE or path == 'dummy_creds.json'
        self.mock_creds_from_file.return_value = self.mock_creds
        self.mock_creds.valid = True

        client = GoogleTasksClient(credentials_path='dummy_creds.json')
        
        self.mock_creds_from_file.assert_called_once_with(TOKEN_FILE, SCOPES)
        self.mock_flow_from_secrets.assert_not_called() # Should not run OAuth flow
        self.mock_build.assert_called_once_with('tasks', 'v1', credentials=self.mock_creds)
        self.assertIsNotNone(client.service)

    @patch('google.oauth2.credentials.Credentials.refresh')
    def test_authentication_token_exists_expired_refreshable(self, mock_refresh):
        self._reset_auth_mocks()
        self.mock_os_exists.side_effect = lambda path: path == TOKEN_FILE or path == 'dummy_creds.json'
        self.mock_creds_from_file.return_value = self.mock_creds
        self.mock_creds.valid = False # Token is not valid
        self.mock_creds.expired = True # Token is expired
        self.mock_creds.refresh_token = "fake_refresh_token" # Token has a refresh token

        client = GoogleTasksClient(credentials_path='dummy_creds.json')

        self.mock_creds_from_file.assert_called_once_with(TOKEN_FILE, SCOPES)
        mock_refresh.assert_called_once_with(Request()) # Request() should be from google.auth.transport.requests
        self.mock_file_open_builtin.assert_called_with(TOKEN_FILE, 'w') # Should save refreshed token
        self.mock_flow_from_secrets.assert_not_called()
        self.mock_build.assert_called_once_with('tasks', 'v1', credentials=self.mock_creds)
        self.assertIsNotNone(client.service)

    def test_authentication_no_token_run_flow(self):
        self._reset_auth_mocks()
        # Simulate no token.json, but credentials.json exists
        self.mock_os_exists.side_effect = lambda path: path == 'dummy_creds.json' 
        self.mock_creds_from_file.return_value = None # No token loaded

        mock_flow_instance = self.mock_flow_from_secrets.return_value
        mock_flow_instance.run_local_server.return_value = self.mock_creds # OAuth flow returns new creds

        client = GoogleTasksClient(credentials_path='dummy_creds.json')

        self.mock_creds_from_file.assert_called_once_with(TOKEN_FILE, SCOPES) # Attempted to load token
        self.mock_flow_from_secrets.assert_called_once_with('dummy_creds.json', SCOPES)
        mock_flow_instance.run_local_server.assert_called_once_with(port=0)
        self.mock_file_open_builtin.assert_called_with(TOKEN_FILE, 'w') # Save new token
        self.mock_build.assert_called_once_with('tasks', 'v1', credentials=self.mock_creds)

    def test_authentication_credentials_file_not_found(self):
        self._reset_auth_mocks()
        self.mock_os_exists.return_value = False # Simulate no token.json AND no credentials.json
        self.mock_creds_from_file.return_value = None

        with self.assertRaisesRegex(FileNotFoundError, "Credentials file not found at non_existent_creds.json"):
            GoogleTasksClient(credentials_path='non_existent_creds.json')
        
        self.mock_flow_from_secrets.assert_not_called()


    def test_get_task_lists(self):
        self.mock_service.tasklists().list().execute.return_value = {'items': [{'id': 'list1', 'title': 'List One'}]}
        lists = self.client.get_task_lists()
        self.assertEqual(len(lists), 1)
        self.assertEqual(lists[0]['title'], 'List One')
        self.mock_service.tasklists().list().execute.assert_called_once()

    def test_get_task_lists_api_error(self):
        self.mock_service.tasklists().list().execute.side_effect = HttpError(MagicMock(status=500), b"Server Error")
        with patch('builtins.print') as mock_print:
            lists = self.client.get_task_lists()
            self.assertEqual(lists, [])
            mock_print.assert_any_call(unittest.mock.ANY) # Check if print was called with error message

    def test_get_task_list_by_title_found(self):
        self.client.get_task_lists = MagicMock(return_value=[
            {'id': 'list1', 'title': 'Work'},
            {'id': 'list2', 'title': 'Personal'}
        ])
        found_list = self.client.get_task_list_by_title('Personal')
        self.assertEqual(found_list['id'], 'list2')

    def test_get_task_list_by_title_not_found(self):
        self.client.get_task_lists = MagicMock(return_value=[
            {'id': 'list1', 'title': 'Work'}
        ])
        found_list = self.client.get_task_list_by_title('Shopping')
        self.assertIsNone(found_list)

    def test_create_task_list(self):
        self.mock_service.tasklists().insert(body={'title': 'New List'}).execute.return_value = {'id': 'list2', 'title': 'New List'}
        new_list = self.client.create_task_list(title='New List')
        self.assertEqual(new_list['title'], 'New List')
        self.mock_service.tasklists().insert.assert_called_with(body={'title': 'New List'})

    def test_create_task_list_api_error(self):
        self.mock_service.tasklists().insert(body={'title': 'New List'}).execute.side_effect = HttpError(MagicMock(status=403), b"Forbidden")
        with patch('builtins.print') as mock_print:
            new_list = self.client.create_task_list(title='New List')
            self.assertIsNone(new_list)
            mock_print.assert_any_call(unittest.mock.ANY)

    def test_delete_task_list(self):
        self.mock_service.tasklists().delete(tasklist='list1').execute.return_value = None # Delete usually returns empty
        with patch('builtins.print') as mock_print:
            self.client.delete_task_list(task_list_id='list1')
            mock_print.assert_called_with("Task list ID 'list1' deleted successfully.")

    def test_delete_task_list_not_found(self):
        # Simulate HttpError with a response object that has a 'status' attribute
        mock_resp = MagicMock()
        mock_resp.status = 404
        self.mock_service.tasklists().delete(tasklist='list1').execute.side_effect = HttpError(mock_resp, b"Not Found")
        with patch('builtins.print') as mock_print:
            self.client.delete_task_list(task_list_id='list1')
            mock_print.assert_called_with("Task list ID 'list1' not found. Could not delete.")
            
    def test_delete_task_list_other_api_error(self):
        mock_resp = MagicMock()
        mock_resp.status = 500
        self.mock_service.tasklists().delete(tasklist='list1').execute.side_effect = HttpError(mock_resp, b"Server Error")
        with patch('builtins.print') as mock_print:
            self.client.delete_task_list(task_list_id='list1')
            self.assertTrue("An API error occurred while deleting task list ID 'list1'" in mock_print.call_args[0][0])


    def test_clear_all_task_lists_and_tasks(self):
        # Mock get_task_lists to return a list of lists to delete
        self.client.get_task_lists = MagicMock(return_value=[{'id': 'list1', 'title': 'List One'}, {'id': 'list2', 'title': 'List Two'}])
        # Mock delete_task_list
        self.client.delete_task_list = MagicMock() # This will be called by the method under test

        self.client.clear_all_task_lists_and_tasks()
        
        self.assertEqual(self.client.delete_task_list.call_count, 2)
        self.client.delete_task_list.assert_any_call('list1')
        self.client.delete_task_list.assert_any_call('list2')

    def test_clear_all_task_lists_no_lists(self):
        self.client.get_task_lists = MagicMock(return_value=[])
        self.client.delete_task_list = MagicMock()
        with patch('builtins.print') as mock_print:
            self.client.clear_all_task_lists_and_tasks()
            self.client.delete_task_list.assert_not_called()
            mock_print.assert_any_call("No task lists found to delete.")


    def test_create_task_simple(self):
        task_body = {'title': 'Test Task'} 
        self.mock_service.tasks().insert(tasklist='list1', body=task_body, parent=None).execute.return_value = {'id': 'task1', 'title': 'Test Task'}
        
        task = self.client.create_task(task_list_id='list1', title='Test Task')
        self.assertEqual(task['title'], 'Test Task')
        self.mock_service.tasks().insert.assert_called_with(tasklist='list1', body=task_body, parent=None)

    def test_create_task_with_details(self):
        due_date_str = "2024-03-10"
        # Expected RFC3339 format for Google Tasks API
        expected_due_api_format = datetime.strptime(due_date_str, '%Y-%m-%d').isoformat() + 'Z'
        
        task_body = {'title': 'Test Task', 'notes': 'Some notes', 'due': expected_due_api_format}
        self.mock_service.tasks().insert(tasklist='list1', body=task_body, parent=None).execute.return_value = {'id': 'task1', **task_body}
        
        task = self.client.create_task(task_list_id='list1', title='Test Task', notes='Some notes', due_date_str=due_date_str)
        self.assertEqual(task['title'], 'Test Task')
        self.assertEqual(task['notes'], 'Some notes')
        self.assertEqual(task['due'], expected_due_api_format)
        self.mock_service.tasks().insert.assert_called_with(tasklist='list1', body=task_body, parent=None)

    def test_create_task_with_invalid_due_date(self):
        task_body = {'title': 'Test Task'} # Due date should not be included if invalid
        self.mock_service.tasks().insert(tasklist='list1', body=task_body, parent=None).execute.return_value = {'id': 'task1', **task_body}
        
        with patch('builtins.print') as mock_print:
            task = self.client.create_task(task_list_id='list1', title='Test Task', due_date_str="invalid-date")
            self.assertEqual(task['title'], 'Test Task')
            self.assertNotIn('due', task) # Due date should not be set
            mock_print.assert_any_call("Invalid due date format: invalid-date. Please use YYYY-MM-DD.")
        self.mock_service.tasks().insert.assert_called_with(tasklist='list1', body=task_body, parent=None)


    def test_create_sub_task(self):
        sub_task_body = {'title': 'Sub Task'}
        self.mock_service.tasks().insert(tasklist='list1', body=sub_task_body, parent='parent_task_id').execute.return_value = {'id': 'subtask1', 'title': 'Sub Task'}

        sub_task = self.client.create_task(task_list_id='list1', title='Sub Task', parent_task_id='parent_task_id')
        self.assertEqual(sub_task['title'], 'Sub Task')
        self.mock_service.tasks().insert.assert_called_with(tasklist='list1', body=sub_task_body, parent='parent_task_id')

    def test_create_task_api_error(self):
        self.mock_service.tasks().insert(tasklist='list1', body={'title': 'Test Task'}, parent=None).execute.side_effect = HttpError(MagicMock(status=500), b"Server Error")
        with patch('builtins.print') as mock_print:
            task = self.client.create_task(task_list_id='list1', title='Test Task')
            self.assertIsNone(task)
            mock_print.assert_any_call(unittest.mock.ANY)


    def test_get_tasks_in_list(self):
        self.mock_service.tasks().list(tasklist='list1', showCompleted=False, showHidden=False).execute.return_value = {
            'items': [{'id': 'task1', 'title': 'Active Task'}]
        }
        tasks = self.client.get_tasks_in_list('list1')
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['title'], 'Active Task')

    def test_get_tasks_in_list_show_completed_hidden(self):
        self.mock_service.tasks().list(tasklist='list1', showCompleted=True, showHidden=True).execute.return_value = {
            'items': [{'id': 'task1', 'title': 'Task A'}, {'id': 'task2', 'title': 'Task B'}]
        }
        tasks = self.client.get_tasks_in_list('list1', show_completed=True, show_hidden=True)
        self.assertEqual(len(tasks), 2)
        self.mock_service.tasks().list.assert_called_with(tasklist='list1', showCompleted=True, showHidden=True)

    def test_get_tasks_in_list_api_error(self):
        self.mock_service.tasks().list(tasklist='list1', showCompleted=False, showHidden=False).execute.side_effect = HttpError(MagicMock(status=500), b"Server Error")
        with patch('builtins.print') as mock_print:
            tasks = self.client.get_tasks_in_list('list1')
            self.assertEqual(tasks, [])
            mock_print.assert_any_call(unittest.mock.ANY)


if __name__ == '__main__':
    unittest.main()
