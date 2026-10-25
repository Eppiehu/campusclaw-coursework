"""Class-filtered PostgreSQL full-text + pgvector ranking with immutable citations."""
import hashlib
import re
from sqlalchemy import select, text
from .models import Chunk, Material, MaterialVersion, KnowledgeGap, LearningEvent


def terms(value):
    words=set(re.findall(r'[a-z0-9]{2,}',value.lower()))
    for phrase in re.findall(r'[\u4e00-\u9fff]+',value):
        words.update(phrase[i:i+2] for i in range(len(phrase)-1))
    return words - {'什么','怎么','如何','请问','一下','介绍','解释','需要','可以','是否'}


def embed(value):
    from app.embeddings import embed_text
    return embed_text(value)


def search(db, user, question, material_ids=None, limit=4, record=True):
    query=(select(Chunk,MaterialVersion,Material).join(MaterialVersion,Chunk.version_id==MaterialVersion.id)
           .join(Material,MaterialVersion.material_id==Material.id)
           .where(Chunk.class_id==user.class_id,Material.class_id==user.class_id,
                  Material.active_version_id==MaterialVersion.id,MaterialVersion.state=='active'))
    if material_ids is not None:
        if not material_ids:return []
        query=query.where(Material.id.in_(material_ids))
    embedding=embed(question)
    vector_rows=db.execute(query.add_columns(Chunk.embedding.cosine_distance(embedding).label('distance'))
                           .order_by(Chunk.embedding.cosine_distance(embedding)).limit(20)).all()
    tokens=terms(question)
    tsquery=' | '.join(sorted(tokens)[:32]) or 'nexus-no-term'
    # PostgreSQL full-text provides the lexical candidates; Chinese substring overlap
    # supplements simple-config tokenization, which does not segment Chinese words.
    lexical=db.execute(query.where(text("to_tsvector('simple', chunks.search_text) @@ to_tsquery('simple', :q)"))
                       .order_by(text("ts_rank_cd(to_tsvector('simple', chunks.search_text),to_tsquery('simple', :q)) DESC"))
                       .params(q=tsquery).limit(20)).all()
    lexical_map={row[0].id:row for row in lexical}
    for row in vector_rows:
        if tokens & terms(row[0].content):lexical_map[row[0].id]=row[:3]
    lexical=sorted(lexical_map.values(),key=lambda r: (-len(tokens & terms(r[0].content)),r[0].id))[:20]
    scores={}; rows={}; similarity={}
    for rank,row in enumerate(vector_rows,1):
        similarity[row[0].id]=1-float(row[3])
        if similarity[row[0].id]>=0.45:
            rows[row[0].id]=row[:3];scores[row[0].id]=1/(60+rank)
    for rank,row in enumerate(lexical,1):
        if tokens & terms(row[0].content):
            rows[row[0].id]=row[:3];scores[row[0].id]=scores.get(row[0].id,0)+1/(60+rank)
    hits=[]
    for cid in sorted(scores,key=lambda x:(-scores[x],x)):
        chunk,version,material=rows[cid]
        overlap=len(tokens & terms(chunk.content))/max(1,len(tokens))
        if overlap<0.12 and similarity.get(cid,0)<0.72:continue
        hits.append(dict(id=len(hits)+1,material_id=material.id,version_id=version.id,version=version.number,
                         sha256=version.sha256,chunk_id=chunk.id,title=material.title,start=chunk.start,end=chunk.end,
                         content=chunk.content,rrf=round(scores[cid],6),similarity=round(similarity.get(cid,0),4)))
        if len(hits)>=limit:break
    if record:
        db.add(LearningEvent(class_id=user.class_id,user_id=user.id,kind='search',details={'query':question,'hits':len(hits)}))
    return hits


def register_gap(db,user,question,before):
    from sqlalchemy.dialects.postgresql import insert
    words=terms(question)
    existing=db.scalars(select(KnowledgeGap).where(KnowledgeGap.class_id==user.class_id,
                           KnowledgeGap.state.in_(['pending','approved','indexing','index_failed']))
                       .with_for_update()).all()
    match=None
    for gap in existing:
        other=terms(gap.question)
        if len(words & other)/max(1,len(words | other))>=0.65:
            match=gap;break
    if match:
        match.heat+=1;match.student_ids=sorted(set(match.student_ids+[user.id]));return match
    fingerprint=hashlib.sha256(' '.join(sorted(words)).encode()).hexdigest()
    statement=insert(KnowledgeGap).values(class_id=user.class_id,fingerprint=fingerprint,question=question,
              student_ids=[user.id],before_hits=before,state='pending',heat=1)
    statement=statement.on_conflict_do_update(index_elements=['class_id','fingerprint'],
                  set_={'heat':KnowledgeGap.heat+1,'state':'pending','after_hits':[]}).returning(KnowledgeGap.id)
    identifier=db.scalar(statement)
    return db.get(KnowledgeGap,identifier)
