"""One local API/CLI surface for private knowledge, confirmed watches and learning."""
import base64
import json
import threading
from .knowledge import Knowledge
from .learning import Learning
from .monitoring import Monitors


class Lifecycle:
    def __init__(self,store,product):self.store,self.product=store,product

    def dispatch(self,area,action,body,background=None):
        project=body.get('project_id')
        if area=='setup':
            from . import setup
            if action=='status':return setup.status(self.store,self.product)
            if action=='model':return setup.save_model(self.store,body['settings'])
            if action=='test':return setup.connection_test(self.store,self.product)
            if action=='sources':return setup.register_sources(self.store,body['source_ids'])
        if area=='feedback':
            from .feedback import Feedback
            service=Feedback(self.store,self.product)
            if action=='save':return service.save(project,body['kind'],body['target'],body['rating'],body.get('note',''),body.get('context',''))
            if action=='list':return {'feedback':service.list(project,body.get('kind'),body.get('context'))}
            if action=='suggestions':return service.suggestions(project,body['monitor_id'])
            if action=='usage':return service.skill_usage(project)
        if area=='desk' and action=='overview':
            from .project_desk import overview
            return overview(self.store,self.product,project)
        if area=='knowledge':
            service=Knowledge(self.store,self.product)
            if action=='create':return service.create(project,body['name'])
            if action=='list':return {'collections':service.list(project),'jobs':service.jobs(project)}
            if action=='import':
                try:raw=base64.b64decode(body['content_base64'],validate=True)
                except (ValueError,TypeError):raise ValueError('Invalid base64 document') from None
                job=service.queue(project,body['collection_id'],body['filename'],raw,body['metadata'],body.get('document_id'))
                if background:
                    try:background(lambda:service.process(project,job['id']))
                    except ValueError:job['note']='Import saved; workers busy. Retry this saved job shortly.'
                    return job
                return service.process(project,job['id'])
            if action=='retry':
                service.job(project,body['id'])
                if background:background(lambda:service.process(project,body['id']));return {'id':body['id'],'state':'queued'}
                return service.process(project,body['id'])
            if action=='search':
                pin=service.pin(project,body['collection_ids'])
                return {'results':service.search(pin,body.get('query',''),filters=body.get('filters'))}
            if action=='read':return service.read(service.pin(project,body['collection_ids']),body['id'])
            if action=='cited':
                run=self.store.get_run(body['run_id'])
                if run['product']!=self.product or run['mission'].get('project_id')!=project:raise ValueError('Cited document outside project/product')
                if not run.get('report') or body['id'] not in run['report'].get('evidence_ids',[]):raise ValueError('Document is not cited by this saved report')
                return service.read(self.store.meta(run['id']).get('knowledge_snapshot'),body['id'])
            if action=='original':return service.original(project,body['collection_id'],body['version'])
            if action=='delete':return service.delete(project,body['collection_id'],body['id'])
            if action=='rebuild':return service.rebuild(project)
        if area=='monitors':
            service=Monitors(self.store,self.product)
            if action=='save':return service.save(project,body['config'],body.get('id'),body.get('expected_revision',0))
            if action=='list':return {'monitors':service.list(project)}
            if action=='preview':return service.preview(project,body['id'])
            if action=='confirm':return service.confirm(project,body['id'],body['hash'])
            if action=='control':return service.control(project,body['id'],body['state'])
            if action=='history':return service.history(project,body['id'])
            if action=='acknowledge':return service.acknowledge(project,body['id'],body['delivery_id'])
            if action=='retry':return service.retry(project,body['id'],body['receipt'])
            if action=='check':
                service.get(project,body['id'])
                if background:background(lambda:service.check(project,body['id']));return {'state':'worker_started','id':body['id']}
                return service.check(project,body['id'])
        if area=='learning':
            service=Learning(self.store,self.product)
            if action=='policy':return service.policy(project,body.get('policy'))
            if action=='status':
                from .feedback import Feedback
                return {'policy':service.policy(project),'skills':service.versions(project),'jobs':service.jobs(project),'usage':Feedback(self.store,self.product).skill_usage(project)}
            if action=='feedback':
                result=service.enqueue(body['run_id'],body.get('lesson',''),project)
                if 'id' in result:
                    if background:
                        try:background(lambda:service.process(result['id']))
                        except ValueError:result['note']='Learning job saved; worker will process it later.'
                    else:result=service.process(result['id'])
                return result
            if action=='process':
                job=next((j for j in service.jobs(project) if j['id']==body['id']),None)
                if not job:raise ValueError('Learning job outside project')
                if background:background(lambda:service.process(body['id']));return {'id':body['id'],'state':'worker_started'}
                return service.process(body['id'])
            if action=='activate':return service.activate(project,body['name'],body.get('version'))
            if action=='export':return service.export(project,body['name'],body['version']).encode('utf-8')
        raise ValueError('Unknown management action')


def worker_tick(store,product):
    watches=Monitors(store,product).tick();learned=Learning(store,product).tick()
    # Supervisor logs carry receipts/status only, never private source excerpts or corrections.
    return {'monitors':[{k:v for k,v in r.items() if k in ('id','monitor_id','state','receipt','considered','fresh','delivery_state')} for r in watches],
            'learning':[{k:v for k,v in r.items() if k in ('id','state','version','error')} for r in learned]}
