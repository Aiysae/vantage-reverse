"""Task idempotency regressions without starting model workers or changing real tasks."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import task_server as server
import vantage_mcp

with tempfile.TemporaryDirectory() as tmp:
    with patch.object(server,'TASKS',Path(tmp)), patch.object(server,'port_for_task',return_value=19800), patch.object(server.codex_auth,'load_codex_credentials'), patch.object(server.threading,'Thread') as thread:
        data={'requirements':'Vantage 集成测试需求','request_id':'vantage-api-regression','rea_enabled':False,'visual_enabled':False}
        first=server.start(data)
        repeated=server.start(dict(data))
        assert first['id']==repeated['id'] and thread.call_count==1
        try:server.start({**data,'requirements':'另外一个不同的集成需求'})
        except ValueError as exc:assert 'request_id' in str(exc)
        else:raise AssertionError('conflicting reuse accepted')
        first['status']='finished';server.save(first)
        assert server.start(data)['status']=='finished' and thread.call_count==1
        for field,value in [('request_id','bad'),('visual_enabled','yes')]:
            try:server.start({**data,'request_id':'fresh-vantage-test',field:value})
            except ValueError:pass
            else:raise AssertionError('invalid input accepted')
        no_site=server.start({'requirements':'没有参考网址的演示需求','rea_enabled':True,'visual_enabled':True})
        assert not no_site['rea_enabled'] and not no_site['visual_enabled']
assert vantage_mcp.summary({'id':'a'*32,'status':'waiting_quota','created_at':0})['terminal'] is False
assert vantage_mcp.summary({'id':'a'*32,'status':'waiting_auth','auth_kind':'website','created_at':0})['requires_input'] is True
print(json.dumps({'status':'PASS','checks':['retry_has_one_task_and_worker','conflicting_request_rejected','terminal_retry_returns_original','invalid_inputs_rejected','no_reference_skips_engines','waiting_states_preserved']}))
