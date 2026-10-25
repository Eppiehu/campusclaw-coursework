"""Official MCP SDK stdio server, re-authenticating every business tool call."""
import json
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from .db import transaction, audit
from .security import authenticate
from .models import Agent, Assignment, Paper, WrongQuestion, Submission, WeeklyReport

server=FastMCP('CampusClaw Nexus')


def execute(name,auth_token,agent_id,**arguments):
    from .retrieval import search
    from .jobs import aggregate_week
    from datetime import timedelta
    from .models import now, week_start
    with transaction() as db:
        user,_=authenticate(db,auth_token)
        agent=db.get(Agent,agent_id)
        try:
            if not agent or agent.class_id!=user.class_id or name not in agent.tools:
                raise PermissionError('工具不在当前应用授权范围')
            if name=='lecture_search':
                result={'hits':search(db,user,arguments['query'],agent.material_ids)}
            elif name=='current_assignments':
                rows=db.scalars(select(Assignment).where(Assignment.class_id==user.class_id,Assignment.state!='draft'))
                result={'assignments':[{'id':a.id,'title':a.title,'deadline':a.deadline.isoformat()} for a in rows]}
            elif name=='my_wrong_questions':
                rows=db.scalars(select(WrongQuestion).where(WrongQuestion.class_id==user.class_id,WrongQuestion.user_id==user.id))
                result={'wrong_questions':[{'id':r.id,'explanation':r.explanation} for r in rows]}
            elif name=='assignment_rubric':
                row=db.get(Assignment,arguments['assignment_id'])
                if not row or row.class_id!=user.class_id or (user.role=='student' and row.state=='draft'):
                    raise PermissionError('作业不可访问')
                result={'assignment_id':row.id,'title':row.title,'rubric':row.rubric}
            elif name=='class_statistics':
                if user.role!='teacher':raise PermissionError('仅教师可查询班级统计')
                start=week_start()
                result=aggregate_week(db,user.class_id,start)
            else:raise PermissionError('未知工具')
            audit(db,user,'mcp.tool',agent_id,{'tool':name,'arguments':arguments,'result':result})
            return result
        except Exception:
            audit(db,user,'mcp.denied',agent_id,{'tool':name},success=False);db.commit()
            raise


@server.tool()
def lecture_search(query:str,auth_token:str,agent_id:int)->dict:
    """Search lectures authorized for this class and application; return source snapshots."""
    return execute('lecture_search',auth_token,agent_id,query=query)


@server.tool()
def current_assignments(auth_token:str,agent_id:int)->dict:
    """List published assignments in the authenticated class, without standard answers."""
    return execute('current_assignments',auth_token,agent_id)


@server.tool()
def my_wrong_questions(auth_token:str,agent_id:int)->dict:
    """Read only the authenticated learner's own wrong-question notebook."""
    return execute('my_wrong_questions',auth_token,agent_id)


@server.tool()
def assignment_rubric(assignment_id:int,auth_token:str,agent_id:int)->dict:
    """Read the grading rubric of a permitted assignment; does not expose its answers."""
    return execute('assignment_rubric',auth_token,agent_id,assignment_id=assignment_id)


@server.tool()
def class_statistics(auth_token:str,agent_id:int)->dict:
    """Teacher-only current-class statistics computed from stored business facts."""
    return execute('class_statistics',auth_token,agent_id)


if __name__=='__main__':server.run(transport='stdio')
