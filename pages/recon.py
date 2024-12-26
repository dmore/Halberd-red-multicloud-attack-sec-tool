'''
Page Navigation URL : app/recon
Page Description : Recon page hosts various reconnaissance dashboards providing fast and easy information gathering in a connected environment. 
'''

from dash import html
import dash_bootstrap_components as dbc

page_layout = html.Div(
    [
        # Recon dashboard tabs
        dbc.Tabs(
            [
                dbc.Tab(
                    label="Roles", 
                    tab_id="tab-recon-roles", 
                    labelClassName="halberd-brand-heading text-danger"
                ),
                dbc.Tab(
                    label="Users", 
                    tab_id="tab-recon-users", 
                    labelClassName="halberd-brand-heading text-danger"
                ),
                dbc.Tab(
                    label="Entity Map", 
                    tab_id="tab-recon-entity-map", 
                    labelClassName="halberd-brand-heading text-danger"
                )
            ],
            id="recon-target-tabs",
            active_tab="tab-recon-roles",
            class_name="bg-halberd-dark"
        ),
        # Div to display recon dashboards
        html.Div(
            id="recon-content-div",
            className="bg-halberd-dark", 
            style={
                "height": "90vh", 
                "justify-content": "center", 
                "align-items": "center"
            }
        ),
    ], 
    className="bg-halberd-dark", 
    style={
        "height": "100vh", 
        "overflow": "auto", 
        "padding-right": "20px", 
        "padding-left": "20px"
    }
)