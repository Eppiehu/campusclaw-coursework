import asyncio
import copy
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TOOL_NAMES={'lecture_search','current_assignments','my_wrong_questions','assignment_rubric','class_statistics'}


def environment():
    allowed={'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','HOME','USERPROFILE','NEXUS_DATABASE_URL',
             'NEXUS_SIGNING_KEY','EMBEDDING_CACHE_DIR','EMBEDDING_MODEL','HF_HUB_OFFLINE'}
    return {k:v for k,v in os.environ.items() if k in allowed}


async def exchange(allowed,token=None,agent_id=None,calls=None):
    params=StdioServerParameters(command=sys.executable,args=['-m','app.nexus.mcp_server'],env=environment())
    async with asyncio.timeout(120):
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                listed=await session.list_tools()
                schemas=[]
                for tool in listed.tools:
                    if tool.name not in allowed or tool.name not in TOOL_NAMES:continue
                    schema=copy.deepcopy(tool.inputSchema)
                    for name in ['auth_token','agent_id']:
                        schema.get('properties',{}).pop(name,None)
                    schema['required']=[x for x in schema.get('required',[]) if x not in ('auth_token','agent_id')]
                    schema['additionalProperties']=False
                    schemas.append({'type':'function','function':{'name':tool.name,'description':tool.description,'parameters':schema}})
                if calls is None:return schemas
                from jsonschema import validate
                definitions={t['function']['name']:t['function']['parameters'] for t in schemas}
                results=[]
                for call in calls:
                    name=call['function']['name']
                    try:
                        if len(calls)>4:raise PermissionError('本轮工具调用超过4次，未执行，请减少调用数量')
                        if name not in definitions:raise PermissionError('未绑定的工具')
                        arguments=json.loads(call['function']['arguments'])
                        validate(arguments,definitions[name])
                        result=await session.call_tool(name,{**arguments,'auth_token':token,'agent_id':agent_id})
                        payload={'isError':bool(result.isError),'content':[c.text for c in result.content if c.type=='text']}
                    except Exception as exc:
                        payload={'isError':True,'error':str(exc)[:200]}
                    results.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(payload,ensure_ascii=False)})
                return results


def discover(allowed):return asyncio.run(exchange(allowed))


def invoke(allowed,token,agent_id,calls):return asyncio.run(exchange(allowed,token,agent_id,calls))
