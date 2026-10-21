"""Explicit real MySQL + Qdrant + local embedding smoke test. No chat-model call."""
import argparse
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.chunks import insert_chunks
from app.db import get_db
from app.hybrid_search import search
from app.vector_store import get_store


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');args=parser.parse_args()
    if not args.live:parser.error('real services require --live')
    if not os.environ.get('DATABASE_URL','').startswith('mysql://'):parser.error('DATABASE_URL must select MySQL')
    app=create_app();title='storage_smoke_'+uuid.uuid4().hex[:8]
    with app.app_context():
        db=get_db();material_id=None
        try:
            version=db.execute('SELECT VERSION() AS version').fetchone()['version']
            material_id=db.execute("INSERT INTO materials (title,class_id,original_filename,stored_path) VALUES (?,'A',?,?)",(title,title+'.md','A/smoke.md')).lastrowid
            content='数学方程学习：检查等式两边是否进行了相同的操作。'
            db.execute("INSERT INTO knowledge_entries (material_id,class_id,content) VALUES (?,'A',?)",(material_id,content))
            insert_chunks(db,material_id,'A',content);db.commit()
            for mode in ('keyword','vector','hybrid'):
                hits=search('数学方程的等式变形','A',mode=mode,material_ids=[material_id])
                assert hits and all(hit['material_id']==material_id for hit in hits),(mode,hits)
                chunk=db.execute('SELECT id,status FROM knowledge_chunks WHERE material_id=?',(material_id,)).fetchone()
                if mode!='keyword':assert chunk['status']=='ready'
                assert hits[0]['chunk_id']==chunk['id']
                print('PASS',mode,'SQL/Qdrant chunk_id consistent')
            assert search('数学方程','B',material_ids=[material_id])==[]
            print('PASS cross-class exclusion; MySQL',version)
        finally:
            if material_id:
                try:get_store().delete_material('A',material_id)
                finally:
                    db.execute('DELETE FROM knowledge_chunks WHERE material_id=?',(material_id,))
                    db.execute('DELETE FROM knowledge_entries WHERE material_id=?',(material_id,))
                    db.execute('DELETE FROM materials WHERE id=?',(material_id,));db.commit()


if __name__=='__main__':main()
