"""Explicit read-only import from the course SQLite archive into a new Nexus class.

Does not send source materials to a remote model. Indexing uses the local embedding.
No credentials or session tokens are copied into an external service.
"""
import argparse
import hashlib
from pathlib import Path
import sqlite3
import sys
from sqlalchemy import select

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.nexus.db import transaction,audit
from app.nexus.models import User,Material,MaterialVersion
from app.nexus.jobs import schedule


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--source-class',required=True)
    parser.add_argument('--target-class',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.source.is_file():parser.error('Source archive does not exist')
    connection=sqlite3.connect(args.source.resolve().as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    materials=connection.execute('SELECT m.title,e.content FROM materials m JOIN knowledge_entries e ON e.material_id=m.id WHERE m.class_id=?',(args.source_class,)).fetchall()
    connection.close()
    print('Archive materials selected:',len(materials),'(contents not printed)')
    if not args.apply:
        print('Dry run only. Use --apply to copy into the explicit Nexus class.');return
    versions=[]
    with transaction() as db:
        owner=db.scalar(select(User).where(User.class_id==args.target_class,User.role=='teacher'))
        if not owner:raise ValueError('Target class must already have a teacher')
        if db.scalar(select(Material.id).where(Material.class_id==args.target_class).limit(1)):
            raise ValueError('Target class must have no materials; import into a new class to avoid overwrite')
        for source in materials:
            material=Material(class_id=owner.class_id,owner_id=owner.id,title=source['title']);db.add(material);db.flush()
            version=MaterialVersion(material_id=material.id,class_id=owner.class_id,number=1,state='indexing',
                                    content=source['content'],sha256=hashlib.sha256(source['content'].encode()).hexdigest())
            db.add(version);db.flush();versions.append(version.id)
        audit(db,owner,'course.imported',details={'count':len(versions),'source_class':args.source_class})
    for identifier in versions:schedule('index',identifier,args.target_class)
    print('Imported and queued:',len(versions))


if __name__=='__main__':main()
