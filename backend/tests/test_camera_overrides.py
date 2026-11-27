import sqlite3
import unittest
from camera_overrides import init_camera_overrides, save_camera_override, apply_camera_overrides

class CameraOverrideTest(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:')
        self.conn.row_factory=sqlite3.Row
        init_camera_overrides(self.conn)
        self.report={'date':'2026-11-28','venues':[
            {'name':'A','deliver':[{'name':'Сотрудник А'},{'name':'Сотрудник Б'}],'held':[{'name':'Сотрудник В'}]},
            {'name':'B','deliver':[{'name':'Сотрудник Г'}],'held':[]}],
            'unmatched':[{'name':'Сотрудник Д','reason':'Не указано'}], 'deliver':3,'held':1,'delivery_venues':2}
    def tearDown(self):
        self.conn.close()
    def test_day_scope_and_restore(self):
        c=self.conn; d=self.report['date']
        save_camera_override(c,d,'Сотрудник А','exclude')
        save_camera_override(c,d,'Сотрудник Г','held')
        out=apply_camera_overrides(c,self.report)
        self.assertEqual((out['deliver'],out['held'],out['delivery_venues']),(1,2,1))
        self.assertEqual(out['excluded'],[{'name':'Сотрудник А','venue':'A'}])
        self.assertEqual(apply_camera_overrides(c,dict(self.report,date='2026-11-29'))['deliver'],3)
        save_camera_override(c,d,'Сотрудник А','reset')
        self.assertEqual(apply_camera_overrides(c,self.report)['deliver'],2)
    def test_venue_and_unmatched(self):
        c=self.conn; d=self.report['date']
        save_camera_override(c,d,'Сотрудник Д','venue','B')
        self.assertEqual(len(apply_camera_overrides(c,self.report)['unmatched']),1)
        save_camera_override(c,d,'Сотрудник Д','delivery')
        out=apply_camera_overrides(c,self.report)
        self.assertEqual(out['deliver'],4)
        self.assertFalse(out['unmatched'])
        save_camera_override(c,d,'Сотрудник Д','exclude')
        self.assertEqual(apply_camera_overrides(c,self.report)['deliver'],3)
        self.assertEqual(len(apply_camera_overrides(c,self.report)['excluded']),1)
    def test_refresh_does_not_mutate_input(self):
        save_camera_override(self.conn,self.report['date'],'Сотрудник А','held')
        apply_camera_overrides(self.conn,self.report)
        self.assertEqual(self.report['venues'][0]['deliver'][0],{'name':'Сотрудник А'})

if __name__=='__main__': unittest.main()
