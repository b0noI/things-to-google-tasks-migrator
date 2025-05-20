import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import peewee
import os
# Add 'src' to sys.path to allow importing 'things_reader'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from things_reader import ThingsReader, TMArea, TMTask # Assuming these are importable

# Define a dummy database for in-memory testing
test_db = peewee.SqliteDatabase(':memory:')

class TestThingsReader(unittest.TestCase):

    def setUp(self):
        # Patch the database path that ThingsReader will use
        self.mock_db_path = ":memory:" 

        # Mock peewee.SqliteDatabase to always return our test_db
        # We are not mocking the class itself, but the instance creation within things_reader.py
        # The global 'db' object in things_reader will be initialized with this test_db
        self.patcher_sqlite_db_init = patch('src.things_reader.db.init', return_value=None)
        self.mock_db_init = self.patcher_sqlite_db_init.start()
        
        # Configure the global 'db' object in things_reader to use our test_db
        from things_reader import db as things_reader_db
        things_reader_db.initialize(test_db) # Use initialize to set the db for models

        # Bind models to the test database for the duration of the test
        # This ensures that any operations on TMArea, TMTask use test_db
        self._original_area_db = TMArea._meta.database
        self._original_task_db = TMTask._meta.database
        TMArea._meta.database = test_db
        TMTask._meta.database = test_db
        
        test_db.connect(reuse_if_open=True)
        test_db.create_tables([TMArea, TMTask], safe=True)

        # Create views as ThingsReader would
        try:
            test_db.execute_sql("CREATE VIEW IF NOT EXISTS TaskView AS SELECT * FROM TMTask WHERE type = 0 AND trashed = 0;")
            test_db.execute_sql("CREATE VIEW IF NOT EXISTS ProjectView AS SELECT * FROM TMTask WHERE type = 1 AND trashed = 0;")
            test_db.execute_sql("CREATE VIEW IF NOT EXISTS HeadingView AS SELECT * FROM TMTask WHERE type = 2 AND trashed = 0;")
        except peewee.OperationalError as e:
            # print(f"setUp view creation error: {e}") # a T&L test comment
            pass 

        # Now, initialize ThingsReader. It should use the already patched and configured db.
        self.reader = ThingsReader(db_path=self.mock_db_path)
        # The reader's __init__ will call db.connect(), which is fine for an in-memory db.


    def tearDown(self):
        self.patcher_sqlite_db_init.stop()
        
        test_db.drop_tables([TMArea, TMTask], safe=True)
        try:
            test_db.execute_sql("DROP VIEW IF EXISTS TaskView;")
            test_db.execute_sql("DROP VIEW IF EXISTS ProjectView;")
            test_db.execute_sql("DROP VIEW IF EXISTS HeadingView;")
        except peewee.OperationalError as e:
            # print(f"tearDown view drop error: {e}") # a T&L test comment
            pass
        
        test_db.close()
        
        # Restore original database meta for models to avoid interference between tests or with other parts of an application
        TMArea._meta.database = self._original_area_db
        TMTask._meta.database = self._original_task_db


    def test_get_areas(self):
        TMArea.create(uuid='area1', title='Work Area', trashed=0)
        TMArea.create(uuid='area2', title='Personal Area', trashed=0)
        TMArea.create(uuid='area3', title='Trashed Area', trashed=1) 

        areas = self.reader.get_areas()
        self.assertEqual(len(areas), 2) 
        self.assertIn({'uuid': 'area1', 'title': 'Work Area'}, [dict(a) for a in areas])
        self.assertIn({'uuid': 'area2', 'title': 'Personal Area'}, [dict(a) for a in areas])

    def test_get_projects(self):
        area1 = TMArea.create(uuid='area1', title='Work')
        TMTask.create(uuid='proj1', title='Project Alpha', type=1, area=area1, trashed=0, notes='Alpha notes') 
        TMTask.create(uuid='proj2', title='Project Beta', type=1, trashed=0, notes='Beta notes') # No area
        TMTask.create(uuid='proj3', title='Trashed Project', type=1, area=area1, trashed=1)


        projects = self.reader.get_projects()
        self.assertEqual(len(projects), 2)
        
        project_data_alpha = next(p for p in projects if p['uuid'] == 'proj1')
        self.assertEqual(project_data_alpha['title'], 'Project Alpha')
        self.assertEqual(project_data_alpha['area_uuid'], 'area1')
        self.assertEqual(project_data_alpha['notes'], 'Alpha notes')

        project_data_beta = next(p for p in projects if p['uuid'] == 'proj2')
        self.assertEqual(project_data_beta['title'], 'Project Beta')
        self.assertIsNone(project_data_beta['area_uuid'])


    def test_get_tasks_for_project(self):
        area1 = TMArea.create(uuid='area1', title='Work')
        proj1 = TMTask.create(uuid='proj1', title='Project Alpha', type=1, area=area1, trashed=0)
        # Tasks directly under project (no heading)
        TMTask.create(uuid='task1', title='Task 1 for Proj1', type=0, project=proj1, trashed=0, notes="Task 1 notes", dueDate=datetime(2024,1,1))
        TMTask.create(uuid='task2', title='Task 2 for Proj1 (trashed)', type=0, project=proj1, trashed=1)
        # Task under a heading - should NOT be returned by this function
        heading1 = TMTask.create(uuid='head1', title='Heading 1', type=2, project=proj1, trashed=0)
        TMTask.create(uuid='task3', title='Task under Heading', type=0, project=proj1, heading=heading1, trashed=0)
        
        tasks = self.reader.get_tasks_for_project(project_uuid='proj1')
        self.assertEqual(len(tasks), 1)
        task_data = dict(tasks[0])
        self.assertEqual(task_data['title'], 'Task 1 for Proj1')
        self.assertEqual(task_data['notes'], 'Task 1 notes')
        self.assertEqual(task_data['due_date'], datetime(2024,1,1))

    def test_get_headings_for_project(self):
        area1 = TMArea.create(uuid='area1', title='Work')
        proj1 = TMTask.create(uuid='proj1', title='Project Alpha', type=1, area=area1, trashed=0)
        TMTask.create(uuid='head1', title='Planning Phase', type=2, project=proj1, trashed=0)
        TMTask.create(uuid='head2', title='Execution Phase', type=2, project=proj1, trashed=0)
        TMTask.create(uuid='head3', title='Trashed Heading', type=2, project=proj1, trashed=1)

        headings = self.reader.get_headings_for_project(project_uuid='proj1')
        self.assertEqual(len(headings), 2)
        heading_titles = [h['title'] for h in headings]
        self.assertIn('Planning Phase', heading_titles)
        self.assertIn('Execution Phase', heading_titles)

    def test_get_tasks_for_heading(self):
        area1 = TMArea.create(uuid='area1', title='Work')
        proj1 = TMTask.create(uuid='proj1', title='Project Alpha', type=1, area=area1, trashed=0)
        heading1 = TMTask.create(uuid='head1', title='Design Tasks', type=2, project=proj1, trashed=0)
        TMTask.create(uuid='taskA', title='Draft UI', type=0, heading=heading1, project=proj1, trashed=0, notes="Draft notes", dueDate=datetime(2024,2,15))
        TMTask.create(uuid='taskB', title='Review UI', type=0, heading=heading1, project=proj1, trashed=0)
        TMTask.create(uuid='taskC', title='Trashed Task under Heading', type=0, heading=heading1, project=proj1, trashed=1)

        tasks = self.reader.get_tasks_for_heading(heading_uuid='head1')
        self.assertEqual(len(tasks), 2)
        task_titles = [t['title'] for t in tasks]
        self.assertIn('Draft UI', task_titles)
        self.assertIn('Review UI', task_titles)
        
        task_a_data = next(t for t in tasks if t['uuid'] == 'taskA')
        self.assertEqual(task_a_data['notes'], 'Draft notes')
        self.assertEqual(task_a_data['due_date'], datetime(2024,2,15))


    def test_get_tasks_standalone(self):
        # Area and Project for context, but not directly linked to standalone tasks
        area1 = TMArea.create(uuid='area1', title='Personal')
        proj1 = TMTask.create(uuid='proj1', title='Home Reno', type=1, area=area1, trashed=0)
        
        # Standalone tasks (no project, some with area, some without)
        TMTask.create(uuid='taskS1', title='Buy Groceries', type=0, area=area1, trashed=0, dueDate=datetime(2024,3,1))
        TMTask.create(uuid='taskS2', title='Book Appointment', type=0, trashed=0) # No area
        TMTask.create(uuid='taskS3', title='Trashed Standalone', type=0, area=area1, trashed=1)
        
        # Task belonging to a project - should NOT be in the main get_tasks() result if we interpret get_tasks() as "all non-project, non-heading tasks"
        # However, the current implementation of get_tasks in ThingsReader fetches ALL tasks of type 0.
        # This means it will include tasks that are part of projects as well.
        # Let's test according to the current implementation.
        TMTask.create(uuid='taskP1', title='Project Task 1', type=0, project=proj1, area=area1, trashed=0)

        all_tasks = self.reader.get_tasks() # type=0, trashed=0
        
        # Expected: taskS1, taskS2, taskP1
        self.assertEqual(len(all_tasks), 3) 
        
        task_titles = [t['title'] for t in all_tasks]
        self.assertIn('Buy Groceries', task_titles)
        self.assertIn('Book Appointment', task_titles)
        self.assertIn('Project Task 1', task_titles)

        task_s1_data = next(t for t in all_tasks if t['uuid'] == 'taskS1')
        self.assertEqual(task_s1_data['area_uuid'], 'area1')
        self.assertEqual(task_s1_data['due_date'], datetime(2024,3,1))
        self.assertIsNone(task_s1_data['project_uuid']) # Standalone

        task_s2_data = next(t for t in all_tasks if t['uuid'] == 'taskS2')
        self.assertIsNone(task_s2_data['area_uuid'])
        self.assertIsNone(task_s2_data['project_uuid']) # Standalone

        task_p1_data = next(t for t in all_tasks if t['uuid'] == 'taskP1')
        self.assertEqual(task_p1_data['project_uuid'], 'proj1') # Part of project

    def test_no_data_scenarios(self):
        self.assertEqual(self.reader.get_areas(), [])
        self.assertEqual(self.reader.get_projects(), [])
        self.assertEqual(self.reader.get_tasks(), [])
        self.assertEqual(self.reader.get_headings_for_project('nonexistent_proj'), [])
        self.assertEqual(self.reader.get_tasks_for_project('nonexistent_proj'), [])
        self.assertEqual(self.reader.get_tasks_for_heading('nonexistent_head'), [])

    def test_reader_initialization_file_not_found(self):
        # Stop the init patcher to test the actual db.init call in ThingsReader's constructor
        self.patcher_sqlite_db_init.stop() 
        
        # Patch os.path.exists to simulate file not found for the db_path
        with patch('os.path.exists', return_value=False):
            with self.assertRaises(FileNotFoundError):
                ThingsReader(db_path="non_existent_path.sqlite")
        
        # Restart it for other tests if setUp is not run for each test method (though it is with unittest.TestCase)
        self.patcher_sqlite_db_init.start() 


if __name__ == '__main__':
    unittest.main()
