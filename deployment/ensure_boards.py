import json
import pathlib
import urllib.request

ORIGIN = 'https://twenty.isty.ist'
ENDPOINT = 'http://127.0.0.1:13020/metadata'


def graphql(query, variables=None, token=None):
    headers = {'Content-Type': 'application/json', 'Origin': ORIGIN, 'Host': 'twenty.isty.ist'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({'query': query, 'variables': variables or {}}).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    if result.get('errors'):
        raise RuntimeError(json.dumps(result['errors']))
    return result['data']


def main():
    credentials = json.loads(pathlib.Path('/opt/isty-twenty/admin.json').read_text())
    login = graphql(
        'mutation($email:String!,$password:String!){signIn(email:$email,password:$password){availableWorkspaces{availableWorkspacesForSignIn{id loginToken}}}}',
        credentials,
    )
    workspaces = login['signIn']['availableWorkspaces']['availableWorkspacesForSignIn']
    workspace_id = pathlib.Path('/opt/isty-twenty/workspace-id').read_text().strip()
    workspace = next(item for item in workspaces if item['id'] == workspace_id)
    data = graphql(
        'mutation($token:String!,$origin:String!){getAuthTokensFromLoginToken(loginToken:$token,origin:$origin){tokens{accessOrWorkspaceAgnosticToken{token}}}}',
        {'token': workspace['loginToken'], 'origin': ORIGIN},
    )
    token = data['getAuthTokensFromLoginToken']['tokens']['accessOrWorkspaceAgnosticToken']['token']

    def execute(query, variables=None):
        return graphql(query, variables, token)

    data = execute('{objects(paging:{first:100}){edges{node{id nameSingular isActive fields(paging:{first:100}){edges{node{id name options}}}}}} getViews{id name type objectMetadataId mainGroupByFieldMetadataId viewFields{fieldMetadataId} viewGroups{fieldValue}} navigationMenuItems{id name viewId userWorkspaceId}}')
    task = next(edge['node'] for edge in data['objects']['edges'] if edge['node']['nameSingular'] == 'task')
    if not task['isActive']:
        raise RuntimeError('Tasks object is inactive')
    fields = {edge['node']['name']: edge['node'] for edge in task['fields']['edges']}
    results = []
    for position, (name, view_type, icon) in enumerate((('Доска задач', 'TABLE', 'IconCheckbox'), ('Канбан', 'KANBAN', 'IconLayoutKanban'))):
        candidates = [view for view in data['getViews'] if view['name'] == name and view['objectMetadataId'] == task['id']]
        if candidates:
            view = candidates[0]
            if view['type'] != view_type:
                raise RuntimeError(f'{name}: unexpected view type')
        else:
            payload = {'name': name, 'objectMetadataId': task['id'], 'type': view_type, 'icon': icon, 'position': position + 3, 'visibility': 'WORKSPACE'}
            if view_type == 'KANBAN':
                payload['mainGroupByFieldMetadataId'] = fields['status']['id']
                payload['shouldHideEmptyGroups'] = False
            view = execute('mutation($input:CreateViewInput!){createView(input:$input){id name type objectMetadataId mainGroupByFieldMetadataId viewFields{fieldMetadataId} viewGroups{fieldValue}}}', {'input': payload})['createView']
        present_fields = {item['fieldMetadataId'] for item in view['viewFields']}
        missing_fields = [{'viewId': view['id'], 'fieldMetadataId': fields[field]['id'], 'position': index, 'isVisible': True, 'size': 220 if field == 'title' else 150} for index, field in enumerate(('title', 'status', 'assignee', 'dueAt')) if fields[field]['id'] not in present_fields]
        if missing_fields:
            execute('mutation($inputs:[CreateViewFieldInput!]!){createManyViewFields(inputs:$inputs){id}}', {'inputs': missing_fields})
        if view_type == 'KANBAN':
            if view['mainGroupByFieldMetadataId'] != fields['status']['id']:
                raise RuntimeError('Kanban must group by task status')
            present_groups = {item['fieldValue'] for item in view['viewGroups']}
            missing_groups = [{'viewId': view['id'], 'fieldValue': option['value'], 'position': option['position'], 'isVisible': True} for option in fields['status']['options'] if option['value'] not in present_groups]
            if missing_groups:
                execute('mutation($inputs:[CreateViewGroupInput!]!){createManyViewGroups(inputs:$inputs){id}}', {'inputs': missing_groups})
        if not any(item['viewId'] == view['id'] and item['userWorkspaceId'] is None for item in data['navigationMenuItems']):
            execute('mutation($input:CreateNavigationMenuItemInput!){createNavigationMenuItem(input:$input){id}}', {'input': {'type': 'VIEW', 'viewId': view['id'], 'name': name, 'icon': icon, 'position': position - 2}})
        results.append({'name': name, 'viewId': view['id'], 'type': view_type})
    verified = execute('{getViews{id viewFields{fieldMetadataId} viewGroups{fieldValue isVisible}} navigationMenuItems{viewId userWorkspaceId}}')
    for board in results:
        view = next(item for item in verified['getViews'] if item['id'] == board['viewId'])
        assert len(view['viewFields']) >= 4
        assert any(item['viewId'] == board['viewId'] and item['userWorkspaceId'] is None for item in verified['navigationMenuItems'])
        if board['type'] == 'KANBAN':
            assert {'TODO', 'IN_PROGRESS', 'DONE'} <= {item['fieldValue'] for item in view['viewGroups'] if item['isVisible']}
    print(json.dumps(results, ensure_ascii=True))


if __name__ == '__main__':
    main()
