# Motivation

This is a dashboard for the agentic PA pipeline. It is needed so that users can monitor where the data is moving as it is processed. It is also important for maintaining the health of the system.

# Context

This is the specification for the dashboard to be created for the prior authorization system defined in the [architecture](architecture.md) document. 

# Requirements

1. Pipeline visualizer  
2. Prior Authorization Request Search
3. Prior Authorization Visualizer 
4. AWS analytics

## Pipeline Visualizer
1. This should be a visualization of the entire pipeline from inputting the data until the email. Each stage should have its own icon. 
2. Have a tab pop up for each stage of the pipeline when clicked.
    - Each tab:
        - Show all the existing prior authorizations at that stage of the pipeline.
        - When clicking on one of the prior authorization requests, it should show some data. This data will be things like how many rejections the request has already had, what the request is for, who is the doctor handling the request, and the patient's name. It should also include a thing to click that leads to the prior authorization visualizer.
    - If a particular stage of the pipeline is broken, it should be highlighted in red; otherwise, green. Clicking on the tab will pop up an error report, which is a summary of the information in AWS analytics.
3. For cool visuals, have a little gradient that sweeps over the pipeline visualization from left to right. When it hits the right end, it will restart from the left. The color of the gradient should match the color of the stage.

## Prior Authorization Request Search
1. I should be able to search for any prior authorization that is in flight using the patient's name. When I click on it, it should send me to the Prior Authorization Visualizer.

## Prior Authorization Visualizer
1. This is a visualizer for the entire prior authorization request, so it includes any relevant patient information and documents relevant to the prior authorization request, like the form that is actually being sent.
2. This should go to a different page. I should be able to return to the dashboard in the state that I left when I clicked on the prior authorization.
3. I should be able to click on the PDF related to the prior authorization that is being visualized and see the full PDF. Make sure that I can scroll when the PDF is many pages. I should be able to return to the prior authorization visualizer by pressing a button.

## AWS analytics
1. This section is to monitor the health of the system.
2. I should have a module that lists all the AWS components being used and whether they are down or not. There will be many components, so make this module scrollable.
3. There should be a module that shows the health of all the databases.
4. Add anything else that a dashboard like this should have. The main thing is that when an error occurs, it should appear in this dashboard and be associated with the corresponding AWS element that failed.
5. The Pipeline Visualizer uses this to show which stages of the pipeline are green or red, and a summary of the error when clicked on when red.

## AWS Ownership

This spec owns:
- **CloudWatch Metrics/Alarms** — Defines custom metrics, alarm thresholds, and aggregation rules for all AWS components. Individual services publish metrics to CloudWatch; this dashboard defines what gets monitored and alerted on.

This spec reads from:
- **DynamoDB Streams** (on `pa_requests`, owned by [Agent Pipeline](agent_pipeline.md)) — Powers real-time WebSocket updates for the pipeline visualizer.
- **DynamoDB: `pa_requests`** (owned by [Agent Pipeline](agent_pipeline.md)) — For PA search and pipeline stage views.
- **S3: `pa-completed-forms`** (owned by [Document Population](document_population.md)) — For PDF viewing in the PA Visualizer.

## API Integration

Communicates with the backend via:
- **REST**: `GET /pa-requests` (search), `GET /pa-requests/:id` (detail)
- **WebSocket**: `WS /ws/pa-status` (real-time pipeline stage updates)
- **REST**: `GET /aws/health` (CloudWatch metrics aggregation)
