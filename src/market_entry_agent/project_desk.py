"""A project-scoped, read-only view of work already saved in the private workspace."""
import json
from .memory import project_id
from .continuity import ResearchMemory
from .knowledge import Knowledge
from .monitoring import Monitors


def overview(store, product, project, limit=20):
    project_id(project)
    recent=[];more=False
    with store.tasks() as db:
        cursor=db.execute('SELECT r.id,r.mission,r.state,r.engine,r.updated FROM runs r JOIN project_runs p ON p.run_id=r.id WHERE r.product=? AND p.product=? AND p.project_id=? ORDER BY r.updated DESC,r.rowid DESC LIMIT ?',(product,product,project,limit+1))
        for row in cursor:
            mission=json.loads(row['mission'])
            if mission.get('project_id')!=project:continue
            if len(recent)>=limit:more=True;break
            recent.append(dict(id=row['id'],question=mission['question'],state=row['state'],engine=row['engine'],updated=row['updated'],
                               countries=mission['countries'],topics=mission['topics'],task_mode=mission.get('task_mode',''),
                               knowledge_ids=mission.get('knowledge_ids',[])))
        sources={};questions=[]
        for item in recent:
            row=db.execute('SELECT report FROM runs WHERE id=?',(item['id'],)).fetchone()
            report=json.loads(row['report']) if row['report'] else {}
            item['title']=report.get('title','');item['summary']=report.get('summary','')[:2000]
            item['next_checks']=report.get('follow_up',[])[:8]
            for source in report.get('sources',[]):
                key=source.get('id')
                if key and key not in sources:sources[key]={k:source[k] for k in ('id','title','url','published_at','retrieval_kind','document_location','document_version','visibility') if k in source}
            note=db.execute('SELECT content FROM research_notes WHERE run_id=?',(item['id'],)).fetchone()
            if note:
                for q in json.loads(note['content']).get('questions',[]):
                    if q.get('status')!='answered':questions.append(dict(q,run_id=item['id']))
    notes=ResearchMemory(store,product).list(project)
    groups={kind:[n for n in notes if n.get('kind')==kind][:20] for kind in ('source_fact','hypothesis','judgment','decision_proposal','operator_decision')}
    libraries=Knowledge(store,product).list(project)
    watches=Monitors(store,product).list(project)
    return {'project_id':project,'product':product,'recent':recent,'has_more_runs':more,'memory':groups,'open_questions':questions[:30],
            'sources':list(sources.values())[:40],
            'collections':[dict(id=c['id'],name=c['name'],documents=len(c['documents'])) for c in libraries],
            'monitors':[dict(id=m['id'],name=m['config']['name'],state=m['state']) for m in watches],
            'scope':'Saved private project only; no network, model call or automatic decision change.'}
