def test_openapi_matches_routes(system):
    _,_,app=system
    response=app.test_client().get('/api/nexus/openapi.json')
    assert response.status_code==200
    doc=response.json
    assert '/api/nexus/login' in doc['paths']
    assert '/api/nexus/papers/{identifier}/submit' in doc['paths']
    assert doc['paths']['/api/nexus/login']['post']['security']==[]
    assert doc['paths']['/api/nexus/materials']['post']['security']==[{'bearerAuth':[]}]
