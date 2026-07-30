from app.models import AIAgent, DataAsset
from app.services.policy import evaluate

def agent(**kw):
    base=dict(key='a',name='A',owner='Security',business_purpose='test',framework='mcp',models='private',allowed_domains='Finance',max_sensitivity='Confidential',allowed_destinations='private-model',approval_status='Approved',risk_level='Medium')
    base.update(kw); return AIAgent(**base)
def asset(**kw):
    base=dict(source='aws-s3',external_id='x',name='payroll.csv',path='s3://x/payroll.csv',business_domain='Finance',sensitivity='Restricted',classification_confidence=.95,public_access=False)
    base.update(kw); return DataAsset(**base)
def test_restricted_exceeds_ceiling_is_denied(): assert evaluate(agent(),asset(),'openai','send','summary')['decision']=='deny'
def test_approved_private_use_can_be_conditional():
    result=evaluate(agent(max_sensitivity='Restricted'),asset(),'private-model','send','forecasting')
    assert result['decision'] in {'allow','conditional'}
    assert 'private-model-only' in result['controls']
