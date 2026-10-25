"""Generate the API inventory from the registered Flask routes."""
import re
from flask import jsonify
from .schemas import Login,AssignmentInput


def document(app):
    schemas={}
    for model in (Login,AssignmentInput):
        schema=model.model_json_schema(ref_template='#/components/schemas/{model}')
        schemas.update(schema.pop('$defs',{}));schemas[model.__name__]=schema
    paths={}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith('/api/nexus/') or rule.rule.endswith('/openapi.json'):continue
        route=re.sub(r'<(?:\w+:)?(\w+)>',r'{\1}',rule.rule)
        for method in sorted(rule.methods-{'OPTIONS','HEAD'}):
            operation={'operationId':rule.endpoint.replace('.','_')+'_'+method.lower(),
              'summary':rule.endpoint.split('.')[-1].replace('_',' '),
              'security':[] if route.endswith('/login') else [{'bearerAuth':[]}],
              'responses':{str(code):{'description':description} for code,description in [(200,'Success'),(201,'Created'),(202,'Task accepted'),(400,'Invalid input'),(401,'Authentication required'),(403,'Role denied'),(404,'Resource unavailable'),(409,'Invalid state')]}}
            parameters=[]
            for name in rule.arguments:parameters.append({'name':name,'in':'path','required':True,'schema':{'type':'integer' if '<int:'+name+'>' in rule.rule else 'string'}})
            if parameters:operation['parameters']=parameters
            if method in ('POST','PATCH'):
                reference='Login' if route.endswith('/login') else 'AssignmentInput' if route.endswith('/assignments') else None
                if reference:operation['requestBody']={'required':True,'content':{'application/json':{'schema':{'$ref':'#/components/schemas/'+reference}}}}
            paths.setdefault(route,{})[method.lower()]=operation
    return {'openapi':'3.0.3','info':{'title':'CampusClaw Nexus API','version':'1.0.0'},'paths':paths,
            'components':{'schemas':schemas,'securitySchemes':{'bearerAuth':{'type':'http','scheme':'bearer','bearerFormat':'JWT'}}}}
