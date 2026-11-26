import sqlite3
import unittest
from fastapi import HTTPException
from frame_stock import init_frames, apply_change, read_frames, Change

class FrameStockTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        with self.db: init_frames(self.db)
        self.actor={'tg_id':1,'full_name':'Test'}
    def tearDown(self):
        self.db.close()
    def change(self,kind,**kwargs):
        revision=self.db.execute('SELECT revision FROM frame_stock WHERE id=1').fetchone()[0]
        with self.db:
            return apply_change(self.db,Change(position=1,kind=kind,revision=revision,**kwargs),self.actor)
    def test_lifecycle(self):
        self.assertEqual(len(read_frames(self.db)['rows']),8)
        self.assertIsNone(read_frames(self.db)['rows'][0]['total'])
        self.change('inventory',boxes=2)
        self.change('unpack',boxes=1)
        self.change('transfer',packs=2,destination='Маэстро')
        r=read_frames(self.db)
        self.assertEqual(r['rows'][0]['total'],900)
        self.assertEqual(r['rows'][0]['packs'],8)
        self.assertEqual(r['rows'][0]['usage'],[100,100,100])
        self.assertEqual(r['shipments'][0]['quantity'],100)
        self.change('inventory',boxes=1,packs=7)
        self.assertEqual(read_frames(self.db)['rows'][0]['usage'],[100,100,100])
        self.change('receipt',packs=1)
        self.change('minimum',minimum=1000)
        self.assertTrue(read_frames(self.db)['rows'][0]['low'])
    def test_reject(self):
        with self.assertRaises(HTTPException): self.change('transfer',packs=1,destination='Маэстро')
        self.change('inventory',packs=2)
        with self.assertRaises(HTTPException): self.change('transfer',packs=3,destination='Маэстро')
        with self.assertRaises(HTTPException): self.change('transfer',packs=1)
        with self.assertRaises(HTTPException):
            apply_change(self.db,Change(position=1,kind='inventory',revision=0),self.actor)
        self.assertEqual(read_frames(self.db)['rows'][0]['total'],100)

if __name__=='__main__':
    unittest.main()
