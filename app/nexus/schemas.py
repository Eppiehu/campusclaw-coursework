from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Login(Strict):
    username:str=Field(min_length=1,max_length=64)
    password:str=Field(min_length=1,max_length=200)


class Criterion(Strict):
    name:str=Field(min_length=1,max_length=100)
    points:float=Field(gt=0,le=100)


class AssignmentInput(Strict):
    title:str=Field(min_length=1,max_length=200)
    question_template:str=Field(min_length=1,max_length=4000)
    ranges:dict[str,list[int]]
    answer_expression:str=Field(min_length=1,max_length=200)
    rubric:list[Criterion]=Field(min_length=1,max_length=10)
    deadline:str

    @model_validator(mode='after')
    def valid(self):
        import re
        for key,bounds in self.ranges.items():
            if not re.fullmatch('[a-z][a-z0-9_]{0,15}',key) or len(bounds)!=2 or not -10000<=bounds[0]<=bounds[1]<=10000:
                raise ValueError('参数名或范围不合法')
        if not self.ranges or len(self.ranges)>5:raise ValueError('参数数量须为1到5')
        if sum(c.points for c in self.rubric)!=100:raise ValueError('Rubric总分必须为100')
        return self


class GradeItem(Strict):
    criterion:str
    score:float=Field(ge=0,le=100)
    reason:str=Field(min_length=1,max_length=1500)


class Grade(Strict):
    items:list[GradeItem]=Field(min_length=1,max_length=10)
    feedback:str=Field(min_length=1,max_length=3000)


class WeeklyComment(Strict):
    observations:list[str]=Field(max_length=6)
    suggestions:list[str]=Field(max_length=6)
    evidence_keys:list[str]=Field(max_length=12)
