# Self Improvement Pipeline

Handles prior authorization rejections by analyzing feedback, improving applications, and resubmitting appeals. Invoked by [Agent Pipeline](agent_pipeline.md) Step 7 on rejection.

## Rejection with Reasons

When a rejection includes a description of the reasons, search through the patient's data to make necessary fixes and resend the prior authorization using the existing pipeline components. Integrate the feedback into additional context that is provided at all stages of the pipeline. On success, save the feedback into the [Memory](memory_feature.md) subsystem.

## Rejection without Reasons

When a rejection provides no reasoning, propose potential reasoning in an experimental format. Iterate through a ranked list of most likely helpful to least likely helpful changes, and use informed guesses to maximize chances in the appeals process. On success, save the successful brainstormed change into the [Memory](memory_feature.md) subsystem.
