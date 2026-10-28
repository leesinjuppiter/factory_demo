"""仅供课程联调：结果由固定规则产生，不是真实推理。"""
class TeachingAdapter:
    def __init__(self,weights):pass
    def load(self):
        return {'name':'TEACHING-ONLY-FAKE','classes':[{'id':0,'name':'example','label':'教学示例','color':'#177b68'}],'box_type':'obb','device':'not-real-inference','sha256':'example-only'}
    def predict(self,image,**params):
        detections=[] if image.max()==0 else [{'id':1,'class_id':0,'class_name':'example','confidence':.9,'polygon':[[5.,2.],[15.,5.],[12.,15.],[2.,12.]]}]
        return {'detections':detections,'timing_ms':{'preprocess':0.,'inference':0.,'postprocess':0.}}
