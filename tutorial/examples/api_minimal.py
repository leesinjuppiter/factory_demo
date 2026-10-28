"""教学最小 API：没有数据库、没有模型、没有完整任务状态机。"""
from fastapi import FastAPI
from pydantic import BaseModel,Field
app=FastAPI(title='教学最小 API — 示例数据')
class Request(BaseModel):
    source_id:str=Field(min_length=1)
    confidence:float=Field(default=.25,ge=.001,le=1)
@app.get('/api/health')
def health():return {'status':'ok','mode':'teaching-only'}
@app.post('/api/runs',status_code=201)
def create_run(request:Request):
    return {'id':'example-not-persisted','status':'example','config':request.model_dump()}
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8877)
