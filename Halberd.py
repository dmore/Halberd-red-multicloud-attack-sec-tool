#!/usr/bin/env python3
import json
import dash
import datetime
import time
import os
import boto3
import uuid
import dash_daq as daq
import dash_bootstrap_components as dbc
from dash import dcc, html, Patch, ALL
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from core.entra.entra_token_manager import EntraTokenManager
from core.azure.azure_access import AzureAccess
from pages.dashboard.entity_map import GenerateEntityMappingGraph
from core.Functions import DisplayTechniqueInfo, TechniqueOptionsGenerator, TabContentGenerator, InitializationCheck, DisplayPlaybookInfo, AddNewSchedule, GetAllPlaybooks, ParseTechniqueResponse, playbook_viz_generator
from core.playbook.playbook import Playbook
from core.playbook.playbook_step import PlaybookStep
from core.playbook.playbook_error import PlaybookError
from core.Constants import *
from core.aws.aws_session_manager import SessionManager
from attack_techniques.technique_registry import *
from core.logging.logger import setup_logger,StructuredAppLog
from pages.attack_trace import group_events,create_summary, parse_log_file
from core.logging.report import read_log_file, analyze_log, generate_html_report
import pandas as pd

# Create Application
app = dash.Dash(__name__,  external_stylesheets=[dbc.themes.LUX, dbc.icons.BOOTSTRAP],title='Halberd', update_title='Loading...', suppress_callback_exceptions=True)

# Navigation bar layout
navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Access", href="/access")),
        dbc.NavItem(dbc.NavLink("Attack", href="/attack")),
        dbc.NavItem(dbc.NavLink("Recon", href="/recon")),
        dbc.NavItem(dbc.NavLink("Automator", href="/automator")),
        dbc.NavItem(dbc.NavLink("Trace", href="/attack-trace")),
    ],
    brand= html.Div([
        dbc.Row(
                [
                    dbc.Col(html.Img(src="/assets/favicon.ico", height="30px")),
                    dbc.Col(html.Div("Halberd", className="text-danger", style={'font-family':'horizon'})),
                ],
            ),
        ]),
    brand_href="/home",
    color="dark",
    dark=True,
)

# App layout
app.layout = html.Div([
    dcc.Interval(id='interval-to-trigger-initialization-check',interval=60000,n_intervals=0),
    html.Div(id='hidden-div', style={'display':'none'}),
    dcc.Location(id='url', refresh=False),
    navbar,
    html.Div(id='page-content',className="bg-dark", style={'overflow': 'auto'}),
    dbc.Toast(
        children = "Hello!",
        id="app-welcome-notification",
        header="Welcome to Halberd",
        is_open=True,
        dismissable=True,
        duration=5000,
        color="primary",
        style={"position": "fixed", "top": 66, "right": 10, "width": 350},
    ),
    dbc.Toast(
        children = "",
        id="app-notification",
        header="Notification",
        is_open=False,
        dismissable=True,
        duration=5000,
        color="primary",
        style={"position": "fixed", "top": 66, "right": 10, "width": 350},
    ),
    dcc.Download(id="app-download-sink"),
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Technique Details")),
            dbc.ModalBody(id = "app-technique-info-display-modal-body"),
            dbc.ModalFooter(
                dbc.Button("Close", id="close-app-technique-info-display-modal", className="ml-auto")
            ),
        ],
        id="app-technique-info-display-modal",
        size="lg",
        scrollable=True,
    ),
    # Error modal -> use this to display an error pop up message
    dbc.Modal(
    [
        dbc.ModalHeader("Error", style={"background-color": "#dc3545", "color": "white"}),
        dbc.ModalBody(id="app-error-display-modal-body"),
        dbc.ModalFooter(
            dbc.Button("Close", id="close-app-error-display-modal", className="ml-auto")
        ),
    ],
    id="app-error-display-modal",
    is_open=False,
    ),
    # Success modal -> use this to display a success pop up message
    dbc.Modal(
    [
        dbc.ModalHeader("Success", style={"background-color": "#28a745", "color": "white"}),
        dbc.ModalBody(id="app-success-display-modal-body"),
        dbc.ModalFooter(
            dbc.Button("Close", id="close-app-success-display-modal", className="ml-auto")
        ),
    ],
    id="app-success-display-modal",
    is_open=False,
)
])

'''C001 - Callback to update the page content based on the URL'''
@app.callback(Output('page-content', 'children'), [Input('url', 'pathname')])
def display_page(pathname):
    if pathname == '/home':
        from pages.home import page_layout
        return page_layout
    elif pathname == '/access':
        from pages.access import page_layout
        return page_layout
    elif pathname == '/attack':
        from pages.attack import page_layout
        return page_layout
    elif pathname == '/recon':
        from pages.recon import page_layout
        return page_layout
    elif pathname == '/attack-trace':
        from pages.attack_trace import generate_attack_trace_view
        return generate_attack_trace_view()
    elif pathname == '/automator':
        from pages.automator import page_layout
        return page_layout
    elif pathname == '/schedules':
        from pages.schedules import GenerateAutomatorSchedulesView
        return GenerateAutomatorSchedulesView()
    else:
        from pages.home import page_layout
        return page_layout

'''C002 - Callback to display tab content'''
@app.callback(Output("tabs-content-div", "children"), Input("attack-surface-tabs", "active_tab"))
def TabSwitcher(tab):
    tab_content = TabContentGenerator(tab)
    return tab_content

'''C003 - Callback to display options in Attack page'''
@app.callback(
        Output(component_id = "technique-options-div", component_property = "children"), 
        State(component_id = "attack-surface-tabs", component_property = "active_tab"), 
        Input(component_id = "tactic-dropdown", component_property = "value"))
def DisplayAttackTechniqueOptions(tab, tactic):
    return TechniqueOptionsGenerator(tab, tactic)


'''C004 - Callback to display technique config'''
@app.callback(
        Output(component_id = "attack-config-div", component_property = "children"), 
        Input(component_id = "attack-options-radio", component_property = "value"),
        prevent_initial_call=True)
def DisplayAttackTechniqueConfig(technique):

    technique_config = TechniqueRegistry.get_technique(technique)().get_parameters()

    config_div_elements = []
    
    config_div_display = Patch()
    config_div_display.clear()

    # Check if technique requires input
    if len(technique_config.keys()) > 0:
        config_div_elements.append(html.H5("Attack Technique Config"))
        for input_field, input_config in technique_config.items():
            # Indicate required fields with * on GUI
            if input_config['required']:
                config_div_elements.append(dbc.Label(input_config['name']+" *"))
            else:
                config_div_elements.append(dbc.Label(input_config['name']))

            if input_config['input_field_type'] in ["text", "email", "password", "number"]:
                config_div_elements.append(dbc.Input(
                    type = input_config['input_field_type'],
                    # Display default values in placeholder for technique param
                    placeholder = input_config['default'] if input_config['default'] else "",
                    debounce = True,
                    id = {"type": "technique-config-display", "index": input_field},
                    className="bg-dark border",
                ))
            elif input_config['input_field_type'] == "bool":
                config_div_elements.append(daq.BooleanSwitch(
                    id = {"type": "technique-config-display-boolean-switch", "index": input_field}, 
                    on=input_config['default'])
                )
            elif input_config['input_field_type'] == "upload":
                config_div_elements.append(dcc.Upload(
                    id = {"type": "technique-config-display-file-upload", "index": input_field}, 
                    children=html.Div([html.A('Drag and Drop or Select a File')]), 
                    style={'width': '100%', 'height': '60px', 'lineHeight': '60px', 'borderWidth': '1px', 'borderStyle': 'dashed', 'borderRadius': '5px', 'textAlign': 'center', 'margin': '10px'})
                )
                
            config_div_elements.append(html.Br())

        config_div = html.Div(config_div_elements, className='divBorder d-grid col-6 mx-auto', style={'width' : '100%'})
        config_div_display.append(config_div)
    else:
        config_div_display.append(html.H5("Attack Technique Config"))
        config_div_display.append(html.B("No config required! Hit 'Execute'"))

    config_div_display.append(html.Br())
    config_div_display.append(
        (html.Div([
            dbc.Button("Execute Technique", id="technique-execute-button", n_clicks=0, color="danger"),
            html.Br(),
        ], className="d-grid col-6 mx-auto"))
    )
    config_div_display.append(html.Div([
            # opens modal and displays technique info in {app-technique-info-display-modal}
            dbc.Button("About Technique", id="technique-info-display-button", n_clicks=0, color="primary"), 
            html.Br(),
            dbc.Button("Add to Playbook", id="open-add-to-playbook-modal-button", n_clicks=0, color="secondary")
        ], style={'display': 'flex', 'justify-content': 'center', 'gap': '10px'})
    )
    
    config_div_display.append(
        html.Div(id='attack-technique-sink-hidden-div', style={'display':'none'}),
    )

    # create plabook dropdown content
    playbook_dropdown_options = []    
    for pb in GetAllPlaybooks():
        playbook_dropdown_options.append(
            {
                "label": html.Div([Playbook(pb).name], style={'font-size': 20}, className="text-dark"),
                "value": Playbook(pb).name,
            }
        )

    config_div_display.append(
        # create add to playbook modal
        dbc.Modal(
            [
                dbc.ModalHeader("Add Technique to Playbook"),
                dbc.ModalBody([
                    dbc.Label("Select Playbook to Add Step"),
                    dcc.Dropdown(
                        options = playbook_dropdown_options, 
                        value = None, 
                        id='att-pb-selector-dropdown',
                        placeholder="Select Playbook",
                        ),
                    html.Br(),
                    dbc.Label("Add to Step # (Optional)", className="text-light"),
                    dbc.Input(id='pb-add-step-number-input', placeholder="3", type= "number", className="bg-dark text-light"),
                    html.Br(),
                    dbc.Label("Wait in Seconds After Step Execution (Optional)", className="text-light"),
                    dbc.Input(id='pb-add-step-wait-input', placeholder="120", type= "number", className="bg-dark text-light")
                ]),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id="close-add-to-playbook-modal-button", className="ml-auto", color="danger", n_clicks=0),
                    dbc.Button("Add to Playbook", id="confirm-add-to-playbook-modal-button", className="ml-2", color="danger", n_clicks=0)
                ])
            ],
            id="add-to-playbook-modal",
            is_open=False,
        )
    )

    return config_div_display

'''C005 - Attack Execution Callback - Execute Technique'''
@app.callback(
        Output(component_id = "execution-output-div", component_property = "children"), 
        Output(component_id = "technique-output-memory-store", component_property = "data"), 
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True), 
        Input(component_id= "technique-execute-button", component_property= "n_clicks"), 
        State(component_id = "tactic-dropdown", component_property = "value"),
        State(component_id = "attack-options-radio", component_property = "value"), 
        State({"type": "technique-config-display", "index": ALL}, "value"), 
        State({"type": "technique-config-display-boolean-switch", "index": ALL}, "on"), 
        State({"type": "technique-config-display-file-upload", "index": ALL}, "contents"), 
        prevent_initial_call = True)
def ExecuteTechniqueCallback(n_clicks, tactic, t_id, values, bool_on, file_content):
    '''The input callback can handle text inputs, boolean flags and file upload content'''
    if n_clicks == 0:
        raise PreventUpdate
    
    technique = TechniqueRegistry.get_technique(t_id)
    technique_params = (technique().get_parameters())

    # Technique attack surface / category
    attack_surface = TechniqueRegistry.get_technique_category(t_id)
    # Active entity / Source
    active_entity = "Unknown"

    if attack_surface in ["m365","entra_id"]:
        manager = EntraTokenManager()
        access_token = manager.get_active_token()
        
        if access_token:
            try:
                access_info = manager.decode_jwt_token(access_token)
                active_entity = access_info['Entity']
            except Exception as e:
                active_entity = "Unknown"
        else: 
            active_entity = "Unknown"
    
    if attack_surface == "aws":
        try:
            manager = SessionManager()
            # set default session
            sts_client = boto3.client('sts')
            session_info = sts_client.get_caller_identity()
            active_entity = session_info['UserId']
        except:
            active_entity = "Unknown"

    if attack_surface == "azure":
        try:
            current_access = AzureAccess().get_current_subscription_info()
            active_entity = current_access['user']['name']
        except:
            active_entity = "Unknown"

    # Create technique input
    technique_input = {}
    file_input = {}
    bool_input = {}
    i=0
    for param in technique_params:
        if technique_params[param]['input_field_type'] not in ["bool", "upload"]: 
            technique_input[param] = [*values][i]
            i+=1
        elif technique_params[param]['input_field_type'] == "upload":
            file_input[param] = technique_params[param]
        elif technique_params[param]['input_field_type'] == "bool":
            bool_input[param] = technique_params[param]
    
    if file_content:
        i = 0
        for param in file_input:
            technique_input[param] = [*file_content][i]
            i+=1

    if bool_on:
        i = 0
        for param in bool_input:
            technique_input[param] = [*bool_on][i]
            i+=1

    # Log technique execution start
    event_id = str(uuid.uuid4()) #Generate unique event_id for the execution
    
    logger.info(StructuredAppLog("Technique Execution",
        event_id = event_id,
        source = active_entity,
        status = "started",
        technique = t_id,
        tactic=tactic,
        timestamp=datetime.datetime.now().isoformat())
    )

    # Execute technique    
    output = technique().execute(**technique_input)
    
    # check if technique output is in the expected tuple format (success, response)
    if isinstance(output, tuple) and len(output) == 2:
        result, response = output

    if result.value == "success":
        # Log technique execution success
        logger.info(StructuredAppLog("Technique Execution",
            event_id = event_id,
            source = active_entity,
            status = "completed",
            result = "success",
            technique = t_id,
            target = None,
            tactic=tactic,
            timestamp=datetime.datetime.now().isoformat())
        )

        # Return results
        return ParseTechniqueResponse(response['value']), response['value'], True, "Technique Execution Successful"
    
    # Log technique execution failure
    logger.info(StructuredAppLog("Technique Execution",
        event_id = event_id,
        source = active_entity,
        status = "completed",
        result = "failed",
        technique = t_id,
        target = None,
        tactic=tactic,
        timestamp=datetime.datetime.now().isoformat())
    )
    
    return ParseTechniqueResponse(response['error']), response['error'], True, "Technique Execution Failed"
    
'''C006 - Entity Map - Generate Map'''
@app.callback(
    Output(component_id = "entity-map-display-div", component_property = "children", allow_duplicate=True),
    Input(component_id = "generate-entity-map-button", component_property = "n_clicks"),
    Input(component_id = "map-layout-select", component_property = "value"),
    Input(component_id = "filter-select", component_property = "value"),
    prevent_initial_call=True
)
def update_entity_map(n_clicks, map_layout, filter_category):
    if not n_clicks:
        return html.Div("Click 'Generate Entity Map' to view the map.")
    
    if filter_category == 'all':
        filter_category = None 

    return GenerateEntityMappingGraph(map_layout, filter_category)

'''C007 - Callback to open/close Technique Info modal'''
@app.callback(
        Output(component_id = "app-technique-info-display-modal", component_property = "is_open", allow_duplicate=True),Output("app-technique-info-display-modal-body", "children", allow_duplicate = True),
        Input(component_id= "technique-info-display-button", component_property= "n_clicks"),
        State(component_id = "attack-options-radio", component_property = "value"), 
        [State("app-technique-info-display-modal", "is_open")], prevent_initial_call=True
)
def DisplayAttackTechniqueConfig(n_clicks, t_id, is_open):
    if n_clicks == 0:
        raise PreventUpdate
    
    # get technique details
    technique_details = DisplayTechniqueInfo(t_id)
    
    return not is_open, technique_details

'''C008 - Callback to generate trace report'''
@app.callback(
    Output(component_id = "app-download-sink", component_property = "data", allow_duplicate=True),
    Input(component_id= "download-trace-report-button", component_property= "n_clicks"),
    prevent_initial_call = True
)
def GenerateTraceReport(n_clicks):
    if n_clicks == 0:
        raise PreventUpdate
    try:
        log_lines = read_log_file(APP_LOG_FILE)
        analysis_results = analyze_log(log_lines)
        html_report = generate_html_report(analysis_results)
        
        # Save the HTML report
        with open(f'{REPORT_DIR}/halberd_security_report.html', 'w', encoding='utf-8') as report_file:
            report_file.write(html_report)
        return dcc.send_file(f'{REPORT_DIR}/halberd_security_report.html')
    except FileNotFoundError:
        return (f"Error: The file '{APP_LOG_FILE}' was not found. Ensure the log file exists and the path is correct.")
    except Exception:
        raise PreventUpdate

'''C009 - Callback to download trace logs'''
@app.callback(
    Output("app-download-sink", "data"),
    Input("download-trace-logs-button", "n_clicks"),
    prevent_initial_call=True,
)
def DownloadTraceLogs(n_clicks):
    if n_clicks == 0:
        raise PreventUpdate
    # Parse log file and create summary
    events = parse_log_file(APP_LOG_FILE)
    grouped_events = group_events(events)
    summary = create_summary(grouped_events)

    # Create DataFrame
    df = pd.DataFrame(summary)
    return dcc.send_data_frame(df.to_csv, "attack_trace.csv", index=False)

'''C010 - Callback to set AWS active/default session and populate AWS access info dynamically based on selected session'''
@app.callback(
        Output(component_id = "aws-access-info-div", component_property = "children"), 
        Input(component_id = "interval-to-trigger-initialization-check", component_property = "n_intervals"), 
        Input(component_id = "aws-session-selector-dropdown", component_property = "value"))
def GenerateAccessInfoDivCallBack(n_interval, session_name):
    # n_intervals will refresh the access info periodically
    info_output_div = []
    if session_name:
        info_output_div.append(html.Br())
        info_output_div.append(html.H5("Access : "))

        manager = SessionManager()
        # set default session
        manager.set_default_session(session_name)
        my_session = manager.get_session(session_name)
        sts_client = my_session.client('sts')
        
        try:
            session_info = sts_client.get_caller_identity()

            info_output_div.append(html.H5("Valid Session", className="text-success"))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("User ID :"))
            info_output_div.append(html.Div(session_info['UserId']))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("Account :"))
            info_output_div.append(html.Div(session_info['Account']))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("ARN : "))
            info_output_div.append(html.Div(session_info['Arn']))
            
            return info_output_div
        except:
            info_output_div.append(html.Div("No Valid Session", className="text-danger"))
            return info_output_div
    else:
        info_output_div.append(html.Div("No Valid Session", className="text-danger"))
        return info_output_div

'''C011 - Callback to populate EntraID access info'''
@app.callback(
        Output(component_id = "access-info-div", component_property = "children"), 
        Input(component_id = "interval-to-trigger-initialization-check", component_property = "n_intervals"))
def GenerateAccessInfoDivCallBack(n_intervals):
    info_output_div = []
    manager = EntraTokenManager()
    access_token = manager.get_active_token()
    
    if access_token:
        try:
            access_info = manager.decode_jwt_token(access_token)
        except Exception as e:
            info_output_div.append(html.Br())
            info_output_div.append(html.Div("Failed to decode access token", className="text-danger"))
            return info_output_div
    else: 
        info_output_div.append(html.Br())
        info_output_div.append(html.Div("No Active Access Token", className="text-danger"))
        return info_output_div
    
    if access_info != None:    
        info_output_div.append(html.Br())
        for info in access_info:
            if info == 'Access Exp':
                if access_info['Access Exp'] < datetime.datetime.fromtimestamp(int(time.time()), tz=datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'):
                    info_output_div += [
                        html.H5(f"{info} : "),
                        html.Div(f"{access_info[info]} UTC [Expired]", className="text-danger"),
                        html.Br(),
                        html.Br()
                        ]
                else:
                    info_output_div += [
                        html.H5(f"{info} : "),
                        html.Div(f"{access_info[info]} UTC [Valid]", className="text-success"),
                        html.Br(),
                        html.Br()
                        ]
            else:
                info_output_div += [
                    html.H5(f"{info} : "), 
                    html.Div(f"{access_info[info]}"), 
                    html.Br(), 
                    html.Br()
                    ]
        
        return info_output_div
    else:
        return "Failed to decode access token"

'''C012 - Callback to select Entra ID access token'''
@app.callback(
        Output(component_id = "access-info-div", component_property = "children",  allow_duplicate=True), 
        Input(component_id = "token-selector-dropdown", component_property = "value"), 
        prevent_initial_call=True)
def UpdateInfoOnTokenSelectCallBack(value):

    manager = EntraTokenManager()

    selected_token = json.loads(value)
    selected_token_entity = list(selected_token.keys())[0]
    selected_token_exp = list(selected_token.values())[0]

    for token in manager.get_all_tokens():
        token_info = manager.decode_jwt_token(token)
        if token_info != None:
            if token_info['Entity'] == selected_token_entity and token_info['Access Exp'] == selected_token_exp:
                access_token = token
                break
        else:
            pass

    manager.set_active_token(access_token)

    access_info = manager.decode_jwt_token(access_token)
    if access_info != None:
        info_output_div = []
        for info in access_info:
            info_output_div = []
        info_output_div.append(html.Br())
        for info in access_info:
            if info == 'Access Exp':
                if access_info['Access Exp'] < datetime.datetime.fromtimestamp(int(time.time()), tz=datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'):
                    info_output_div += [
                        html.H5(f"{info} : "),
                        html.Div(f"{access_info[info]} UTC [Expired]", className="text-danger"),
                        html.Br(),
                        html.Br()
                        ]
                else:
                    info_output_div += [
                        html.H5(f"{info} : "),
                        html.Div(f"{access_info[info]} UTC [Valid]", className="text-success"),
                        html.Br(),
                        html.Br()
                        ]
            else:
                info_output_div += [
                    html.H5(f"{info} : "), 
                    html.Div(f"{access_info[info]}"), 
                    html.Br(), 
                    html.Br()
                    ]
        
        return info_output_div
    else:
        return "No token selected"

'''C013 - Callback to generate Entra ID token options in Access dropdown'''
@app.callback(
        Output(component_id = "token-selector-dropdown", component_property = "options"), 
        Input(component_id = "token-selector-dropdown", component_property = "title"))
def GenerateDropdownOptionsCallBack(title):
    manager = EntraTokenManager()
    if title == None:
        all_tokens = []
        for token in manager.get_all_tokens():
            token_info = manager.decode_jwt_token(token)
            if token_info != None:
                selected_value = {token_info.get('Entity') : token_info.get('Access Exp')}
                all_tokens.append(
                    {
                        'label': html.Div(token_info['Entity'], className="text-dark"), 'value': json.dumps(selected_value)
                    }
                )

        return all_tokens

'''C014 - Recon page tab switcher'''
@app.callback(
        Output("recon-content-div", "children"), 
        Input("recon-target-tabs", "active_tab"))
def TabSwitcher(tab):
    if tab == "tab-recon-entity-map":
        from pages.dashboard.entity_map import page_layout
        return page_layout
    if tab == "tab-recon-roles":
        from pages.dashboard.recon_roles import page_layout
        return page_layout
    if tab == "tab-recon-users":
        from pages.dashboard.recon_users import page_layout
        return page_layout
    else:
        from pages.dashboard.entity_map import page_layout
        return page_layout

'''C015 - Callback to generate data in role recon dashboard'''
@app.callback(
        Output(component_id = "role-name-recon-div", component_property = "children"), 
        Output(component_id = "role-template-id-recon-div", component_property = "children"), 
        Output(component_id = "role-id-recon-div", component_property = "children"), 
        Output(component_id = "role-member-count-recon-div", component_property = "children"), 
        Output(component_id = "role-member-recon-div", component_property = "children"), 
        Output(component_id = "role-description-recon-div", component_property = "children"), 
        Input(component_id= "role-recon-start-button", component_property= "n_clicks"),
        Input(component_id = "role-recon-input", component_property = "value"))
def ExecuteRecon(n_clicks, role_name):
    if n_clicks == 0:
        raise PreventUpdate
    
    # Input validation
    if role_name in ["",None]:
        response = "N/A"
        return response, response, response, response, response, response
    
    # Import recon functions
    from pages.dashboard.recon_roles import FindRole, ReconRoleMembers
    
    # Execute recon
    role_name, role_id, role_template_id, role_description = FindRole(role_name)
    member_count, role_members = ReconRoleMembers(role_template_id)

    return role_name, role_template_id, role_id, member_count, role_members, role_description

'''C016 - Callback to generate data in user recon dashboard'''
@app.callback(Output(
    component_id = "user-displayname-recon-div", component_property = "children"), 
    Output(component_id = "user-id-recon-div", component_property = "children"), 
    Output(component_id = "user-upn-recon-div", component_property = "children"), 
    Output(component_id = "user-mail-recon-div", component_property = "children"), 
    Output(component_id = "user-job-title-recon-div", component_property = "children"), 
    Output(component_id = "user-location-recon-div", component_property = "children"), 
    Output(component_id = "user-phone-recon-div", component_property = "children"), 
    Output(component_id = "user-group-count-recon-div", component_property = "children"), 
    Output(component_id = "user-role-count-recon-div", component_property = "children"), 
    Output(component_id = "user-groups-recon-div", component_property = "children"), 
    Output(component_id = "user-roles-recon-div", component_property = "children"), 
    Output(component_id = "user-app-count-recon-div", component_property = "children"), 
    Output(component_id = "user-app-recon-div", component_property = "children"), 
    Input(component_id= "user-recon-start-button", component_property= "n_clicks"),
    Input(component_id = "user-recon-input", component_property = "value"))
def ExecuteRecon(n_clicks, user_string):
    if n_clicks == 0:
        raise PreventUpdate
    
    # Input validation
    if user_string in ["",None]:
        response = "N/A"
        return response, response, response, response, response, response, response, response, response, response, response, response, response
    
    # Import recon functions
    from pages.dashboard.recon_users import FindUser, ReconUserMemberships, ReconUserAssignedApps

    # Execute recon
    user_id, user_upn, user_display_name, user_mail, user_job_title, user_off_location, user_phone = FindUser(user_string)
    groups_count, role_count, group_membership, role_assigned = ReconUserMemberships(user_id)
    app_assigned_count, user_app_assignments = ReconUserAssignedApps(user_id)

    return user_display_name, user_id, user_upn, user_mail, user_job_title, user_off_location, user_phone, groups_count, role_count, group_membership, role_assigned, app_assigned_count, user_app_assignments

'''C017 - Callback to populate Azure access info dynamically based on selected subscription'''
@app.callback(
        Output(component_id = "azure-access-info-div", component_property = "children"), 
        Input(component_id = "interval-to-trigger-initialization-check", component_property = "n_intervals"), 
        Input(component_id = "azure-subscription-selector-dropdown", component_property = "value"))
def GenerateAccessInfoDivCallBack(n_intervals, value):
    # n_intervals will refresh the access info periodically
    info_output_div = []
    info_output_div.append(html.Br())
    info_output_div.append(html.H5("Access : "))
    
    if value == None:
        # If no subscription is selected, proceed with default subscription
        pass
    else:
        selected_subscription = value
        AzureAccess().set_active_subscription(selected_subscription)

    # Get set subscription info
    current_access = AzureAccess().get_current_subscription_info()
    
    try:
        if current_access != None:
            # Construct session info to display
            info_output_div.append(html.H5("Active Session", className="text-success"))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("Environment Name :"))
            info_output_div.append(html.Div(current_access.get("environmentName", "N/A")))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("Name : "))
            info_output_div.append(html.Div(current_access.get("name", "N/A")))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("Subscription ID : "))
            info_output_div.append(html.Div(current_access.get("id", "N/A")))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("Is Default : "))
            info_output_div.append(html.Div(str(current_access.get("isDefault", "N/A"))))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("State : "))
            info_output_div.append(html.Div(current_access.get("state", "N/A")))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("User : "))
            info_output_div.append(html.Div(current_access.get("user", "N/A").get("name","N/A")))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("Tenant ID : "))
            info_output_div.append(html.Div(current_access.get("tenantId", "N/A")))
            info_output_div.append(html.Br())
            info_output_div.append(html.Br())
            info_output_div.append(html.H5("Home Tenant ID :"))
            info_output_div.append(html.Div(current_access.get("homeTenantId", "N/A")))
            
            return info_output_div
        else:
            info_output_div.append(html.Div("No Active Session", className="text-danger"))
            return info_output_div
    except:
        info_output_div.append(html.Div("No Active Session", className="text-danger"))
        return info_output_div

'''C018 - Callback to generate Azure subscription options in Access dropdown'''
@app.callback(
        Output(component_id = "azure-subscription-selector-dropdown", component_property = "options"), 
        Input(component_id = "azure-subscription-selector-dropdown", component_property = "title"))
def GenerateDropdownOptionsCallBack(title):
    if title == None:
        all_subscriptions = []
        
        for subs in AzureAccess().get_account_available_subscriptions():
            selected_value = subs.get("id")
            all_subscriptions.append(
                {
                    'label': html.Div(subs.get("name"), className="text-dark"), 'value': selected_value
                }
            )

        return all_subscriptions

'''C019 - Callback to generate automated attack sequence visualization'''
@app.callback(
        Output(component_id = "attack-automator-path-display-div", component_property = "children"), 
        Input(component_id = "automator-pb-selector-dropdown", component_property = "value"), 
        prevent_initial_call=True)
def DisplayAttackSequenceViz(selected_pb):
    if selected_pb:
        return playbook_viz_generator(selected_pb)
    else:
        raise PreventUpdate

'''C020 - Callback to execute attack sequence in automator view'''
@app.callback(
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True), 
        Output(component_id = "app-error-display-modal", component_property = "is_open", allow_duplicate=True),
        Output(component_id = "app-error-display-modal-body", component_property = "children", allow_duplicate=True),
        State(component_id = "automator-pb-selector-dropdown", component_property = "value"), 
        Input(component_id = "execute-sequence-button", component_property = "n_clicks"), prevent_initial_call=True)
def ExecuteAttackSequence(playbook_name, n_clicks):
    if n_clicks == 0:
        raise PreventUpdate
    
    if playbook_name == None:
        return False, "", True, "Playbook Execution Aborted - You are missing something : Select a playbook"
    
    # Execute playbook
    for pb in GetAllPlaybooks():
        pb_config = Playbook(pb)
        if pb_config.name == playbook_name:
            playbook_file = pb_config.yaml_file
    try:
        Playbook(playbook_file).execute()
        return True, "Playbook Execution Completed", False, ""
    except PlaybookError as e:
        if e.error_type == "data_error":
            return False, "", True, f"Playbook Execution Aborted - Invalid Playbook : {str(e.message)}"
        else:
            return False, "", True, f"Playbook Execution Failed - Invalid Playbook : {str(e.message)}"
    except Exception as e:
        return False, "", True, f"Playbook Execution Failed - Unexpected Error : {str(e)}"

'''C021 - Callback to open attack scheduler modal'''
@app.callback(
        Output(component_id = "scheduler-modal", component_property = "is_open"), 
        [Input("toggle-scheduler-modal-open-button", "n_clicks"), 
        Input("toggle-scheduler-modal-close-button", "n_clicks")], 
        [State("scheduler-modal", "is_open")])
def toggle_modal(open_trigger, close_trigger, is_open):
    if open_trigger or close_trigger:
        return not is_open
    return is_open

'''C022 - Callback to create new automator schedule'''
@app.callback(
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True), 
        Output(component_id = "scheduler-modal", component_property = "is_open", allow_duplicate=True), 
        Input(component_id = "automator-pb-selector-dropdown", component_property = "value"), 
        Input(component_id = "set-time-input", component_property = "value"), 
        Input(component_id = "automator-date-range-picker", component_property = "start_date"), 
        Input(component_id = "automator-date-range-picker", component_property = "end_date"), 
        Input(component_id = "schedule-repeat-boolean", component_property = "on"), 
        Input(component_id = "repeat-options-dropdown", component_property = "value"), 
        Input(component_id = "schedule-name-input", component_property = "value"), 
        Input(component_id = "schedule-sequence-button", component_property = "n_clicks"), 
        prevent_initial_call=True)
def CreateNewAutomatorSchedule(playbook_id, execution_time, start_date, end_date, repeat_flag, repeat_frequency, schedule_name, n_clicks):
    if n_clicks == 0:
        raise PreventUpdate
    
    # Send notification if no playbook selected from dropdown
    if playbook_id == None:
        return True, "No Playbook Selected to Schedule", False
    
    # Create new schedule
    AddNewSchedule(schedule_name, playbook_id, start_date, end_date, execution_time, repeat_flag, repeat_frequency)

    # Send notification after new schedule is created
    return True, "Playbook Scheduled", False

'''C023 - Callback to export playbook'''
@app.callback(
        Output(component_id = "app-download-sink", component_property = "data", allow_duplicate = True), 
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True),
        Output(component_id = "app-error-display-modal", component_property = "is_open", allow_duplicate=True),
        Output(component_id = "app-error-display-modal-body", component_property = "children", allow_duplicate=True), 
        State(component_id = "automator-pb-selector-dropdown", component_property = "value"), 
        State(component_id = "export-playbook-mask-param-boolean", component_property = "on"),
        State(component_id = "export-playbook-filename-text-input", component_property = "value"),
        Input(component_id = "export-playbook-button", component_property = "n_clicks"), 
        prevent_initial_call=True)
def ExportAttackPlaybook(playbook_name, mask_param, export_file_name, n_clicks):
    if n_clicks == 0:
        raise PreventUpdate
        
    # If no playbook is selected, show error pop-up
    if playbook_name == None:
        return None, False, "", True, "No Playbook Selected to Export"
    
    # Get the selected playbook file name
    for pb in GetAllPlaybooks():
        pb_config = Playbook(pb)
        if  pb_config.name == playbook_name:
            playbook_file = pb_config.yaml_file
            break
    
    if not export_file_name:
        export_file_name = "Halberd_Playbook" # Set default file name
    
    # Export playbook
    playbook_export_file_path = Playbook(playbook_file).export(export_file = export_file_name, include_params=not(mask_param))

    # Download playbook and send app notification
    return dcc.send_file(playbook_export_file_path), True, "Playbook Exported", False, ""

'''C024 - Callback to import playbook'''
@app.callback(
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True),
        Output(component_id = "app-error-display-modal", component_property = "is_open", allow_duplicate=True),
        Output(component_id = "app-error-display-modal-body", component_property = "children", allow_duplicate=True), 
        Input(component_id = 'import-pb-button', component_property = 'n_clicks'), 
        Input(component_id = 'upload-playbook', component_property = 'contents'), 
        prevent_initial_call=True)
def UploadHalberdPlaybook(n_clicks, file_contents):
    if n_clicks == 0:
        raise PreventUpdate

    if file_contents:
        try:
            # Import playbook
            Playbook.import_playbook(file_contents)
            return True, "Playbook Imported", False, ""
        except Exception as e:
            # Display error in modal pop up
            return False, "", True, str(e)
    else:
        raise PreventUpdate

'''C025 - Callback to add technique as step to playbook'''
@app.callback(
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True), 
        Output(component_id = "app-error-display-modal", component_property = "is_open", allow_duplicate=True),
        Output(component_id = "app-error-display-modal-body", component_property = "children", allow_duplicate=True),
        Input(component_id = "confirm-add-to-playbook-modal-button", component_property = "n_clicks"), 
        Input(component_id = "att-pb-selector-dropdown", component_property = "value"), 
        State(component_id = "pb-add-step-number-input", component_property = "value"),
        State(component_id = "pb-add-step-wait-input", component_property = "value"),
        State(component_id = "attack-options-radio", component_property = "value"),
        State(component_id = {"type": "technique-config-display", "index": ALL}, component_property = "value"), 
        State(component_id = {"type": "technique-config-display-boolean-switch", "index": ALL}, component_property = "on"), 
        State(component_id = {"type": "technique-config-display-file-upload", "index": ALL}, component_property = "contents"),
        prevent_initial_call=True
    )
def AddTechniqueToPlaybook(n_clicks, selected_pb, step_no, wait, t_id, values, bool_on, file_content):
    if n_clicks == 0:
        raise PreventUpdate
    
    # If config has file as input
    if selected_pb:
        if file_content:
            for pb in GetAllPlaybooks():
                pb_config = Playbook(pb)
                if  pb_config.name == selected_pb:
                    break

            technique_input.append(file_content)
        
        else:
            for pb in GetAllPlaybooks():
                pb_config = Playbook(pb)
                if  pb_config.name == selected_pb:
                    break
        
        # Create technique input
        technique = TechniqueRegistry.get_technique(t_id)
        technique_params = (technique().get_parameters())

        technique_input = {}
        file_input = {}
        bool_input = {}
        i=0
        for param in technique_params:
            if technique_params[param]['input_field_type'] not in ["bool", "upload"]: 
                technique_input[param] = [*values][i]
                i+=1
            elif technique_params[param]['input_field_type'] == "upload":
                file_input[param] = technique_params[param]
            elif technique_params[param]['input_field_type'] == "bool":
                bool_input[param] = technique_params[param]
        
        if file_content:
            i = 0
            for param in file_input:
                technique_input[param] = [*file_content][i]
                i+=1

        if bool_on:
            i = 0
            for param in bool_input:
                technique_input[param] = [*bool_on][i]
                i+=1

        # Create playbook step
        try:
            new_step = PlaybookStep(module=t_id, params=technique_input, wait=wait)
            
            # Add technique to playbook
            pb_config.add_step(new_step=new_step, step_no=step_no)
            
            # Save and update with new playbook config
            pb_config.save()

            return True, "Added to Playbook", False, ""
        except Exception as e:
            # Display error in error pop-up
            return False, "", True, str(e)
    else:
        # Display error in error pop-up
        return False, "", True, "Cannot Add Step : No Playbook Selected"

'''C026 - Callback to open playbook creator modal'''
@app.callback(
        Output(component_id = "playbook-creator-modal", component_property = "is_open"), 
        [Input("pb-creator-modal-open-button", "n_clicks"), Input("pb-creator-modal-close-button", "n_clicks")], 
        [State("playbook-creator-modal", "is_open")])
def toggle_modal(open_trigger, close_trigger, is_open):
    if open_trigger or close_trigger:
        return not is_open
    return is_open

'''C027 - Callback to create new playbook'''
@app.callback(
        Output(component_id = "playbook-creator-modal", component_property = "is_open", allow_duplicate=True),  
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True), 
        Output(component_id = "app-error-display-modal", component_property = "is_open", allow_duplicate=True),
        Output(component_id = "app-error-display-modal-body", component_property = "children", allow_duplicate=True),
        State(component_id = "pb-name-input", component_property = "value"), 
        State(component_id = "pb-desc-input", component_property = "value"), 
        State(component_id = "pb-author-input", component_property = "value"), 
        State(component_id = "pb-refs-input", component_property = "value"), 
        Input(component_id = "create-playbook-button", component_property = "n_clicks"), prevent_initial_call=True
    )
def CreateNewPlaybookCallback(pb_name, pb_desc, pb_author, pb_references, n_clicks):
    if n_clicks == 0:
        raise PreventUpdate
    
    try:
        new_playbook = Playbook.create_new(
            name= pb_name,
            author= pb_author,
            description= pb_desc,
            references=[pb_references]
        )
        return False, True, f"New Playbook Created : {new_playbook.name}", False, ""
    except Exception as e:
        return True, False, "", True, str(e)
    
'''C028 - Callback to display technique info from playbook node in modal'''
@app.callback(
        Output(component_id = "app-technique-info-display-modal-body", component_property = "children"),
        Output(component_id = "app-technique-info-display-modal", component_property = "is_open"),
        Input(component_id = "auto-attack-sequence-cytoscape-nodes", component_property = "tapNodeData"),
        [State(component_id = "app-technique-info-display-modal", component_property = "is_open")], 
        prevent_initial_call=True
    )
def DisplayPlaybookNodeData(data, is_open):
    if data:
        # Extract module_id from node label
        if data['label'] != "None":
            info = data['info']
        else:
            raise PreventUpdate
        
        if info == "time":
            # Display time gap
            wait_time = data['label']
            return [html.B(f"Time Gap : {wait_time} seconds")], True
        else:
            # Display module info
            pb_step_info = data['info']
            step_data = next(iter(pb_step_info.items()))
            module_id = step_data[1]['Module']
            return DisplayTechniqueInfo(module_id), not is_open
    else:
        raise PreventUpdate
        
'''C029 - Callback to display playbook node data on hover'''
@app.callback(
        Output(component_id = "playbook-node-data-div", component_property = "children", allow_duplicate= True),
        Input(component_id = "auto-attack-sequence-cytoscape-nodes", component_property = "mouseoverNodeData"), 
        State(component_id="automator-pb-selector-dropdown", component_property="value"),
        prevent_initial_call=True
    )
def DisplayPlaybookNodeData(node_data, value):
    if node_data:
        # Extract module_id from node label
        if node_data['label'] != "None":
            info = node_data['info']
        else:
            raise PreventUpdate
        
        if info == "time":
            wait_time = node_data['label']
            return dbc.Card(
                [
                    dbc.CardHeader(html.H5("Time Gap", className="mb-0")),
                    dbc.CardBody(
                        html.P(f"{str(wait_time)} Seconds", className="card-text", style={"white-space": "pre-wrap"})
                    )
                ],
                className="mb-3"
            )
        try:
            # Return module info
            pb_step_info = node_data['info']
            pb_step_config = next(iter(pb_step_info.items()))
            pb_step_no = pb_step_config[0]
            step_data = next(iter(pb_step_info.items()))[1]

            params = step_data.get('Params', {})
            param_cards = []
            if params:
                for key, value in params.items():
                    param_cards.append(
                        dbc.Card([
                            dbc.CardBody([
                                html.H6(key, className="card-subtitle mb-2 text-muted"),
                                html.P(str(value), className="card-text")
                            ])
                        ], className="mb-2")
                    )
            else:
                param_cards.append(
                    dbc.Card([
                        dbc.CardBody([
                            html.P("No parameters", className="card-text text-muted")
                        ])
                    ], className="mb-2")
                )

            param_accordion = dbc.Accordion([
                dbc.AccordionItem(
                    param_cards,
                    title="Parameters",
                )
            ], start_collapsed=True)

            step_content = [
                html.H6(f"Step {pb_step_no}", className="mb-2"),
                html.P(f"Module: {step_data.get('Module', 'N/A')}", className="mb-1"),
                html.P(f"Wait: {step_data.get('Wait', 'N/A')}", className="mb-2"),
                param_accordion
            ]

            step_card = dbc.Card(dbc.CardBody(step_content), className="mb-3")
            
            return dbc.Card(
                [
                    dbc.CardHeader(html.H5("PB_Sequence", className="mb-0")),
                    dbc.CardBody(step_card)
                ],
                className="mb-3"
            )
        except:
            return dbc.Card(
                [
                    dbc.CardHeader(html.H5("Invalid Playbook Node", className="mb-0")),
                    dbc.CardBody(
                        html.P("Nothing to display", className="card-text", style={"white-space": "pre-wrap"})
                    )
                ],
                className="mb-3"
            )
    else:
        raise PreventUpdate

'''C030 - Callback to open/close add to playbook modal on Attack page'''
@app.callback(
    Output(component_id = "add-to-playbook-modal", component_property = "is_open"),
    [
        Input(component_id = "open-add-to-playbook-modal-button", component_property = "n_clicks"), 
        Input(component_id = "close-add-to-playbook-modal-button", component_property = "n_clicks"), 
        Input(component_id = "confirm-add-to-playbook-modal-button", component_property = "n_clicks")
    ],
    [State(component_id = "add-to-playbook-modal", component_property = "is_open")],
    prevent_initial_call=True
)
def toggle_modal(n1, n2, n3, is_open):
    if n1 or n2 or n3:
        return not is_open
    return is_open

'''C031 - Callback to generate playbook options in Automator - Attack Playbook dropdown'''
@app.callback(
        Output(component_id = "automator-pb-selector-dropdown", component_property = "options"), 
        Input(component_id = "automator-pb-selector-dropdown", component_property = "title"))
def GenerateDropdownOptionsCallBack(title):
    if title == None:
        playbook_dropdown_option = []    
        for pb in GetAllPlaybooks():
            
            playbook_dropdown_option.append(
                {
                    "label": html.Div([Playbook(pb).name], style={'font-size': 20}, className="text-dark"),
                    "value": Playbook(pb).name,
                }
            )
        return playbook_dropdown_option
    
'''C032 - Callback to delete playbook'''
@app.callback(
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True), 
        Output(component_id = "app-error-display-modal", component_property = "is_open", allow_duplicate=True),
        Output(component_id = "app-error-display-modal-body", component_property = "children", allow_duplicate=True),
        Input(component_id = "delete-pb-button", component_property = "n_clicks"), 
        State(component_id = "automator-pb-selector-dropdown", component_property = "value"), 
        prevent_initial_call=True)
def DeleteAttackPlaybook(n_clicks, playbook_name):
    if n_clicks == 0:
        raise PreventUpdate
        
    # If no playbook is selected, send notification
    if playbook_name == None:
        return False, "", True, "Delete Error : No Playbook Selected to Delete"
    
    # Get the selected playbook file location
    for pb in GetAllPlaybooks():
        pb_config = Playbook(pb)
        if  pb_config.name == playbook_name:
            playbook_file = pb_config.yaml_file_path

    try:
        os.remove(playbook_file)
        return True, "Playbook Deleted", False, ""
    except Exception as e:
        return False, "", True, str(e)

'''C033 - Callback to open modal and display technique information from home techniques matrix'''
@app.callback(
    Output("app-technique-info-display-modal", "is_open", allow_duplicate=True),
    Output("app-technique-info-display-modal-body", "children", allow_duplicate = True),
    Input({"type": "technique", "index": dash.ALL}, "n_clicks"),
    State("app-technique-info-display-modal", "is_open"),
    prevent_initial_call=True
)
def ToggleAppModalFromHomeMatrix(n_clicks, is_open):
    # Prevent call back on page load
    if any(item is not None for item in n_clicks):
        if not dash.callback_context.triggered:
            return is_open, ""
        
        # Extract technique id
        triggered_id = dash.callback_context.triggered[0]["prop_id"]
        technique_id = eval(triggered_id.split(".")[0])["index"]

        # Generate technique information
        technique_details = DisplayTechniqueInfo(technique_id)
        
        return not is_open, technique_details
    else:
        raise PreventUpdate
    
'''C034 - Callback to close the app technique info modal'''
@app.callback(
    Output("app-technique-info-display-modal", "is_open", allow_duplicate=True),
    Input("close-app-technique-info-display-modal", "n_clicks"),
    State("app-technique-info-display-modal", "is_open"),
    prevent_initial_call=True
)
def CloseAppModal(n_clicks, is_open):
    if n_clicks:
        return False
    return is_open

'''C035 - Callback to download report'''
@app.callback(
    Output("app-download-sink", "data", allow_duplicate=True),
    Input("generate-report-button", "n_clicks"),
    prevent_initial_call=True,
)
def DownloadReport(n_clicks):
    if n_clicks == 0:
        raise PreventUpdate
    # Parse log file and create summary
    events = parse_log_file(APP_LOG_FILE)
    grouped_events = group_events(events)
    summary = create_summary(grouped_events)

    # Create DataFrame
    df = pd.DataFrame(summary)
    return dcc.send_data_frame(df.to_csv, "attack_trace.csv", index=False)

'''C036 - Callback to display entity map node information'''
@app.callback(
    Output("entity-map-node-info-div", "children"),
    Input("entity-detection-cytoscape-nodes", "tapNodeData"),
)
def DisplayEntityMapNodeInfo(data):
    if not data:
        return "Click on a node to see more information."
    return f"Selected Node: {data['label']}"
    
'''C037 - Callback to display playbook information in playook information modal'''
@app.callback(
        Output(component_id = "automator-playbook-info-display-modal", component_property = "is_open", allow_duplicate=True),
        Output("automator-playbook-info-display-modal-body", "children", allow_duplicate = True), 
        Input(component_id= "pb-view-details-button", component_property= "n_clicks"),
        State(component_id = "automator-pb-selector-dropdown", component_property = "value"), 
        prevent_initial_call=True
)
def ShowPlaybookInfo(n_clicks, selected_pb):
    if n_clicks == 0:
        raise PreventUpdate
    
    # If no playbook is selected
    if selected_pb == None:
        raise PreventUpdate
    
    return True, DisplayPlaybookInfo(selected_pb)

'''C038 - Callback to close the playbook information modal'''
@app.callback(
    Output("automator-playbook-info-display-modal", "is_open", allow_duplicate=True),
    Input("close-automator-playbook-info-display-modal", "n_clicks"),
    State("automator-playbook-info-display-modal", "is_open"),
    prevent_initial_call=True
)
def ClosePbInfoModal(n_clicks, is_open):
    if n_clicks:
        return False
    return is_open

'''C039 - Callback to download technique response data'''
@app.callback(
    Output("app-download-sink", "data", allow_duplicate=True),
    Input("download-technique-response-button", "n_clicks"),
    State("technique-output-memory-store", "data"),
    prevent_initial_call=True
)
def DownloadTechniqueRawResponse(n_clicks, data):
    if n_clicks is None or data is None:
        raise PreventUpdate
    
    # Create a file in the outputs directory
    execution_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    output_filepath = f"./output/Response_Export_{execution_time}.txt"
    with open(output_filepath, "w") as f:
        f.write(str(data))
    
    # Download response file
    return dcc.send_file(output_filepath)

'''C040 - Callback to open playbook export modal'''
@app.callback(
        Output(component_id = "export-playbook-modal", component_property = "is_open"), 
        [
            Input("toggle-export-playbook-modal-open-button", "n_clicks"), 
            Input("toggle-export-playbook-modal-close-button", "n_clicks")
        ], 
        [State("export-playbook-modal", "is_open")])
def ToggleModal(open_trigger, close_trigger, is_open):
    if open_trigger or close_trigger:
        return not is_open
    return is_open

'''C041 - Callback to close the app error modal'''
@app.callback(
    Output("app-error-display-modal", "is_open", allow_duplicate=True),
    Input("close-app-error-display-modal", "n_clicks"),
    State("app-error-display-modal", "is_open"),
    prevent_initial_call=True
)
def CloseAppErrorModal(n_clicks, is_open):
    if n_clicks:
        return False
    return is_open

'''C042 - Callback to generate AWS session options in AWS sessions dropdown'''
@app.callback(Output(component_id = "aws-session-selector-dropdown", component_property = "options"), Input(component_id = "aws-session-selector-dropdown", component_property = "title"))
def GenerateDropdownOptionsCallBack(session_name):
    manager = SessionManager()
    if session_name == None:
        all_sessions = []
        for session in manager.list_sessions():
            all_sessions.append(
                {
                    'label': html.Div(session['session_name'], className="text-dark"), 
                    'value': session['session_name']
                }
            )

        return all_sessions

'''C043 - Callback to delete EntraID access token'''
@app.callback(
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True),
        State(component_id = "token-selector-dropdown", component_property = "value"),
        Input(component_id = "del-entra-token-button", component_property = "n_clicks"),
        prevent_initial_call=True
    )
def DeleteEntraTokenCallback(value, n_clicks):
    if n_clicks is None or value is None:
        raise PreventUpdate
    
    # EntraID token manager
    manager = EntraTokenManager()

    # Load the selected token and get token info
    selected_token = json.loads(value)
    selected_token_entity = list(selected_token.keys())[0]
    selected_token_exp = list(selected_token.values())[0]

    # Check token in token list
    for token in manager.get_all_tokens():
        token_info = manager.decode_jwt_token(token)
        if token_info != None:
            if token_info['Entity'] == selected_token_entity and token_info['Access Exp'] == selected_token_exp:
                access_token = token
                break
        else:
            pass
    
    # Delete selected token
    manager.delete_token(access_token)
    return True, "EntraID Token Deleted"

'''C044 - Callback to delete AWS session'''
@app.callback(
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True),
        State(component_id = "aws-session-selector-dropdown", component_property = "value"),
        Input(component_id = "del-aws-session-button", component_property = "n_clicks"),
        prevent_initial_call=True
    )
def DeleteAWSSessionCallback(session_name, n_clicks):
    if n_clicks is None or session_name is None:
        raise PreventUpdate
    
    # AWS session manager
    manager = SessionManager()
    # Delete selected session
    manager.remove_session(session_name)

    return True, "AWS Session Deleted"

'''C045 - Callback to delete Azure session'''
@app.callback(
        Output(component_id = "app-notification", component_property = "is_open", allow_duplicate=True), 
        Output(component_id = "app-notification", component_property = "children", allow_duplicate=True),
        Input(component_id = "del-az-session-button", component_property = "n_clicks"),
        prevent_initial_call=True
    )
def DeleteAzureSessionCallback(n_clicks):
    if n_clicks is None:
        raise PreventUpdate
    
    # Azure access manager
    manager = AzureAccess()
    # Logout selected session
    logout = manager.logout()
    if logout:
        return True, "Azure Session Closed"
    
if __name__ == '__main__':
    # Run Initialization check
    InitializationCheck()
    #Initialize logger
    logger = setup_logger() 
    # Start application
    app.run_server(debug = True)