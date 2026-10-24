"""Private enterprise profiles, comparable entry options, assumptions and delivery stages."""
from .business import Records, choice, fields, fingerprint, identifier, strings, text
from .countries import scope_keys
from .memory import stamp

DIMENSIONS = ('demand','access','channel','delivery','economics','risks')


class Workflow(Records):
    kinds = ('profile','option','assumption','stage','decision','transaction','economics')
    context_kinds = kinds
    agent_kinds = ('option','assumption','stage')

    def __init__(self, store, product='market-entry-agent'):
        super().__init__(store, product)

    def normalize(self, kind, data, as_of=None):
        if kind == 'transaction':
            fields(data,['name','option_id','manufacturer','exporter','seller','importer','buyer','incoterm','responsibility_note'])
            return {'name':text(data.get('name'),200),'option_id':identifier(data.get('option_id')),
                **{k:text(data.get(k,''),500,optional=True) for k in ('manufacturer','exporter','seller','importer','buyer','incoterm')},
                'responsibility_note':text(data.get('responsibility_note'))}
        if kind == 'economics':
            from .economics import normalize
            return normalize(data)
        if kind == 'profile':
            fields(data,['product','buyer','stage','countries','capabilities','constraints','budget'])
            return {'product':text(data.get('product'),500),'buyer':text(data.get('buyer'),500),
                'stage':choice(data.get('stage'),('exploring','targeted','operating')),'countries':strings(data.get('countries',[])),
                **{k:text(data.get(k,''),optional=True) for k in ('capabilities','constraints','budget')}}
        if kind == 'option':
            fields(data,['name','countries','mode','rationale','dimensions','status','evidence_ids','profile_revision','tradeoff','requirements','next_validation'])
            dimensions = data.get('dimensions')
            fields(dimensions,DIMENSIONS)
            out = {'name':text(data.get('name'),200),'countries':strings(data.get('countries')),'mode':text(data.get('mode'),200),
                'rationale':text(data.get('rationale')),'dimensions':{k:text(dimensions.get(k,''),optional=True) for k in DIMENSIONS},
                'status':choice(data.get('status','candidate'),('researching','candidate','selected','deferred','blocked'))}
            if not out['countries']:
                raise ValueError('Entry option needs a target country')
            for key in ('tradeoff','requirements','next_validation'):
                if key in data:out[key]=text(data[key],optional=True)
            out['evidence_ids'] = self.references(data.get('evidence_ids',[]),out['countries'],as_of=as_of)
            if 'profile_revision' in data:
                if type(data['profile_revision']) is not int or data['profile_revision'] < 1:
                    raise ValueError('profile_revision requires a positive integer')
                out['profile_revision'] = data['profile_revision']
            return out
        if kind == 'assumption':
            fields(data,['statement','status','countries','topics','option_ids','stage_ids','evidence_ids','note','blocking','decision_impact','effort','validation_owner','next_test','if_supported','if_not'])
            out = {'statement':text(data.get('statement')),'status':choice(data.get('status','unchecked'),('unchecked','supported','challenged','needs_review')),
                'countries':strings(data.get('countries',[])),'topics':strings(data.get('topics',[])),
                'option_ids':strings(data.get('option_ids',[])), 'stage_ids':strings(data.get('stage_ids',[])),
                'note':text(data.get('note',''),optional=True)}
            if not out['countries'] or not out['topics']:
                raise ValueError('Assumption monitoring requires countries and topics')
            out['evidence_ids'] = self.references(data.get('evidence_ids',[]),out['countries'],out['topics'],as_of)
            if 'blocking' in data:
                if type(data['blocking']) is not bool:raise ValueError('blocking must be boolean')
                out['blocking']=data['blocking']
            for key in ('decision_impact','effort'):
                if key in data:out[key]=choice(data[key],('low','medium','high'))
            for key in ('validation_owner','next_test','if_supported','if_not'):
                if key in data:out[key]=text(data[key],optional=True)
            return out
        if kind == 'stage':
            fields(data,['goal','actions','deliverables','completion_signal','option_id','depends_on','status','note','evidence_ids'])
            return {'goal':text(data.get('goal')),'actions':strings(data.get('actions',[]),15),
                'deliverables':strings(data.get('deliverables',[]),15),'completion_signal':text(data.get('completion_signal')),
                'option_id':identifier(data.get('option_id')), 'depends_on':strings(data.get('depends_on',[]),12),
                'status':choice(data.get('status','planned'),('planned','doing','blocked','done')),
                'note':text(data.get('note',''),optional=True),'evidence_ids':self.references(data.get('evidence_ids',[]),as_of=as_of)}
        if kind == 'decision':
            fields(data,['title','rationale','option_ids','evidence_ids'])
            return {'title':text(data.get('title'),200),'rationale':text(data.get('rationale')),'option_ids':strings(data.get('option_ids',[])),
                'evidence_ids':self.references(data.get('evidence_ids',[]),as_of=as_of)}
        raise ValueError('Unknown entry record kind')

    def validate_links(self, db, project, kind, rid, data, origin):
        old = self.get(db,project,kind,rid)
        if origin == 'agent_proposal' and old and kind in ('option','assumption','stage'):
            initial = {'option':'candidate','assumption':'unchecked','stage':'planned'}[kind]
            if old['data'].get('status') != initial:
                raise ValueError('operator_state_protected: preserve operator decisions and progress')
        if kind == 'profile' and rid != 'main':
            raise ValueError('The active enterprise profile uses ID main')
        if kind == 'option':
            profile = self.get(db,project,'profile','main')
            if not profile:
                raise ValueError('Save the enterprise profile before entry options')
            data.setdefault('profile_revision',profile['revision'])
            if data['profile_revision'] != profile['revision']:
                raise ValueError('Option must use the current profile revision')
            if origin == 'agent_proposal' and data['status'] != 'candidate':
                raise ValueError('Agent options remain candidates; operator selects or defers them')
        if kind == 'assumption':
            if origin == 'agent_proposal' and data['status'] != 'unchecked':
                raise ValueError('Agent assumptions start unchecked')
            for oid in data['option_ids']:
                if not self.get(db,project,'option',oid):
                    raise ValueError('Assumption references an unknown option')
            for sid in data['stage_ids']:
                if not self.get(db,project,'stage',sid):
                    raise ValueError('Assumption references an unknown stage')
        if kind == 'stage':
            if not self.get(db,project,'option',data['option_id']):
                raise ValueError('Stage references an unknown option')
            if origin == 'agent_proposal' and data['status'] != 'planned':
                raise ValueError('Agent stages are proposed plans, not completed work')
            def visit(sid, path):
                if sid == rid or sid in path:
                    raise ValueError('Roadmap dependency cycle')
                dep = self.get(db,project,'stage',sid)
                if not dep:
                    raise ValueError('Unknown prerequisite stage')
                if dep['data']['option_id'] != data['option_id']:
                    raise ValueError('Prerequisite belongs to another option')
                if data['status']=='done' and dep['data']['status']!='done':
                    raise ValueError('Finish prerequisite stages first')
                for child in dep['data']['depends_on']:
                    visit(child,path|{sid})
            for sid in data['depends_on']:
                visit(sid,set())
            if data['status']=='done' and not data['note']:
                raise ValueError('Completed stage requires an operator completion note')
        if kind in ('transaction','economics'):
            if not self.get(db,project,'option',data['option_id']):raise ValueError('Transaction/economics references an unknown option')
            if origin!='operator':raise ValueError('Transaction responsibility and quote inputs require operator entry')
        if kind == 'decision':
            for oid in data['option_ids']:
                if not self.get(db,project,'option',oid):
                    raise ValueError('Decision references an unknown option')

    def matching(self, assumption):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = []
        for row in self.store.export_evidence()['records']:
            if row.get('synthetic') or not isinstance(row.get('published_at'),str) or row.get('retrieval_kind') == 'search_snippet':
                continue
            try:
                published = stamp(row['published_at'])
            except (ValueError, OverflowError):
                continue
            if published <= now and scope_keys(assumption['countries']).intersection(scope_keys(row['countries'])) and set(assumption['topics']).intersection(row['topics']):
                result.append(row['id'])
        return sorted(result)

    def change(self, db, project, command, origin, run=None):
        if not isinstance(command,dict):raise ValueError('Project command must be an object')
        if run and command.get('kind') == 'option':
            snapshot = self.store.meta(run['id']).get('project_state', {}).get('records', {}).get('profile', [])
            if snapshot:
                command = dict(command, data=dict(command['data'], profile_revision=snapshot[0]['revision']))
        before=self.get(db,project,command.get('kind'),command.get('id'))
        result = super().change(db,project,command,origin,run)
        if command['kind']=='economics' and before and not result.get('unchanged'):
            from .economics import calculate
            old=calculate(before['data']);new=calculate(result['data'])
            changed=[k for k in result['data']['values'] if before['data']['values'].get(k)!=result['data']['values'][k]]
            rid=fingerprint(['economics',result['id'],result['revision']])
            self.save(db,project,'review',rid,{'assumption_id':'','statement':'报价或测算条件已更新：'+result['data']['name'],
                'new_evidence_ids':[],'option_ids':[result['data']['option_id']],'stage_ids':[],
                'kind':'economics_changed','changed_inputs':changed,'before':old,'after':new,
                'note':'Operator scenario inputs changed. Compare the arithmetic and responsibility before revising the selected route; selection was not changed automatically.'},0,'runtime')
        if command['kind']=='assumption' and not result.get('unchanged'):
            cursor = self.get(db,project,'assumption_cursor',result['id'])
            # All currently saved matching evidence becomes the baseline; the operator can examine refs.
            self.save(db,project,'assumption_cursor',result['id'],{'seen':self.matching(result['data'])},cursor['revision'] if cursor else 0,'runtime')
        return result

    def state_in(self, db, project):
        value = {'product':self.product,'project_id':project,**{k:self.list(db,project,k) for k in self.kinds},
                 'reviews':self.list(db,project,'review'),'checks':self.list(db,project,'check'),
                 'note':'Operator conditions, proposals and source statements remain distinct. Needs-review means new matching information, not automatic disproof.'}
        profile = next(iter(value['profile']),None)
        value['comparison'] = [{'id':o['id'],'revision':o['revision'],**o['data'],
            'profile_changed':bool(profile and o['data'].get('profile_revision') != profile['revision'])} for o in value['option']]
        from .economics import calculate
        value['economic_scenarios']=[{'id':r['id'],'revision':r['revision'],**r['data'],'calculation':calculate(r['data'])} for r in value['economics']]
        impacts={'low':0,'medium':1,'high':2};effort={'low':0,'medium':1,'high':2}
        pending=[r for r in value['assumption'] if r['data']['status'] in ('unchecked','challenged','needs_review')]
        pending.sort(key=lambda r:(-int(r['data'].get('blocking',False)),-impacts[r['data'].get('decision_impact','medium')],effort[r['data'].get('effort','medium')],r['id']))
        value['validation_queue']=[{'id':r['id'],**r['data'],'rank':i+1,'why_ranked':{'blocking':r['data'].get('blocking',False),'decision_impact':r['data'].get('decision_impact','medium'),'effort':r['data'].get('effort','medium')},'note':'Qualitative operator/proposal labels; ordered by blocker, impact then effort, not a success probability.'} for i,r in enumerate(pending)]
        return value

    def snapshot(self, project):
        value=super().snapshot(project)
        from .economics import calculate
        for row in value['records'].get('economics',[]):row['data']['calculation']=calculate(row['data'])
        pending=[r for r in value['records'].get('assumption',[]) if r['data']['status'] in ('unchecked','challenged','needs_review')]
        importance={'low':0,'medium':1,'high':2}
        pending.sort(key=lambda r:(-int(r['data'].get('blocking',False)),-importance[r['data'].get('decision_impact','medium')],importance[r['data'].get('effort','medium')],r['id']))
        ranks={r['id']:{'rank':i+1,'why_ranked':{k:r['data'].get(k,False if k=='blocking' else 'medium') for k in ('blocking','decision_impact','effort')}} for i,r in enumerate(pending)}
        for row in value['records'].get('assumption',[]):
            if row['id'] in ranks:row['data']['validation_priority']=ranks[row['id']]
        return value

    def check(self, project):
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            return self.evaluate_in(db,project)

    def evaluate_in(self, db, project):
        from .memory import project_id
        project_id(project)
        created = []
        for assumption in self.list(db,project,'assumption'):
            aid, data = assumption['id'], assumption['data']
            cursor = self.get(db,project,'assumption_cursor',aid)
            seen = cursor['data']['seen'] if cursor else data['evidence_ids']
            current = self.matching(data)
            added = sorted(set(current)-set(seen))
            if not added:
                continue
            review_id = fingerprint([aid,added])
            review = {'assumption_id':aid,'statement':data['statement'],'new_evidence_ids':added,
                      'option_ids':data['option_ids'],'stage_ids':data['stage_ids'],
                      'before':{'assumption_status':data['status'],'evidence_ids':data['evidence_ids']},
                      'after':{'assumption_status':'needs_review','new_evidence_ids':added},
                      'affected_decision_ids':[d['id'] for d in self.list(db,project,'decision') if set(d['data']['option_ids']).intersection(data['option_ids'])],
                      'note':'New matching source material. Relevance and effect on this assumption require research; no automatic legal or commercial conclusion.'}
            self.save(db,project,'review',review_id,review,0,'runtime')
            self.save(db,project,'assumption_cursor',aid,{'seen':sorted(set(seen)|set(current))},cursor['revision'] if cursor else 0,'runtime')
            if data['status'] != 'needs_review':
                self.save(db,project,'assumption',aid,dict(data,status='needs_review'),assumption['revision'],'runtime')
            created.append(review_id)
        previous = self.get(db,project,'check','latest')
        from datetime import datetime, timezone
        value = {'evaluated_at':datetime.now(timezone.utc).isoformat(), 'new_review_ids':created,'reviews_created':len(created),'scope':'saved_evidence_only','source_refresh':'not_performed',
                 'note':'This checks saved matching evidence; refresh or research to acquire current sources. Existing reports are preserved.'}
        saved = self.save(db,project,'check','latest',value,previous['revision'] if previous else 0,'runtime')
        return {**value,'checked_at':saved['updated']}

    def guide(self):
        return {'product':self.product,'transaction_and_economics':'Read frozen transaction/economics records via project_state kind and id. Economics include deterministic single-currency calculations with null gaps; quote/role inputs are operator-only. Read assumption validation_priority and conditional next checks. Never infer origin from transit or replace missing prices with zero.','agent_writable_kinds':list(self.agent_kinds), 'dimensions':list(DIMENSIONS),
          'contracts':{
          'option':{'name':'entry option','countries':['mission country'],'mode':'entry channel','rationale':'conditional recommendation',
                    'tradeoff':'what is gained and given up','requirements':'resources and conditions needed; preserve unknown costs','next_validation':'what to verify first and why',
                    'dimensions':{k:'analysis, source basis or unknown' for k in DIMENSIONS},'status':'candidate','evidence_ids':['read ID']},
          'stage':{'goal':'proposed goal','option_id':'existing or earlier new option ID','actions':['work'],'deliverables':['output'],
                   'completion_signal':'observable criterion','depends_on':[],'status':'planned','note':'proposed','evidence_ids':[]},
          'assumption':{'statement':'business premise to validate','status':'unchecked','countries':['mission country'],'topics':['mission topic'],
                        'option_ids':['option ID'],'stage_ids':[],'evidence_ids':['read ID'],'note':'what would change the plan'}},
          'report_extension':'Optional project_update: {commands:[{kind:option/assumption/stage,id:stable_ID,expected_revision:0,data:contract}]}. Read project_state for frozen IDs/revisions and profile. Put new options before stages and assumptions. Operator alone changes profile, selects options, confirms assumptions and marks progress. Save report directly; never invent costs or treat an aggregate country index as enterprise fit.'}
