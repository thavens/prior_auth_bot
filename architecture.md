# Motivation

Applying for prior authorization is a friction point for physicians and patients alike. We would like to automate this process to enable swift care of patients and reduce the load and burnout of physicians.

# Context

We are trying to win a hackathon under the track of best use of AWS. This doesn’t mean use as many services as possible but a genuinely creative and effective use of their products to solve a problem. Assume we have unlimited use of AWS so if you think any service is useful then implement it.  
Example PA form: [https://medi-calrx.dhcs.ca.gov/cms/medicalrx/static-assets/documents/provider/forms-and-information/Medi-Cal\_Rx\_PA\_Request\_Form.pdf\#page=1.00\&gsr=0](https://medi-calrx.dhcs.ca.gov/cms/medicalrx/static-assets/documents/provider/forms-and-information/Medi-Cal_Rx_PA_Request_Form.pdf#page=1.00&gsr=0)

# Requirements

1. Self-improving system  
2. Email service
3. Document population
4. Physician Dashboard
5. Pipeline Dashboard

### Email Service

Use Amazon SES service to send prior authorization email requests to [michael.lavery.2017@gmail.com](mailto:michael.lavery.2017@gmail.com) after one iteration of the pipeline is complete.  
Take responses from Amazon SES and use rejection reasons to improve for appeal.  
On failure brainstorm a priority list of improvements to isolate solutions

# Agent Pipeline

1. Extract anything from appointment transcript and patient data that may require prior authorization, this may be prescriptions, surgeries, and therapies. You can use things like AWS comprehend medical, InferRxNorm, InferSNOMEDCT, and DetectEntitiesV2. You should cast a wide net on what is extracted because it will be determined later what actually requires prior authorization.  
2. Use LLM with the context of treatments, patient data, and healthcare providers to find the treatments that require prior authorization. Use a web agent to scrape the provider’s website to do this. Cache the data that is retrieved from the web agent so it doesn’t scrape every search.  
3. Using prescriptions that require prior authorization and user data, use LLM to search our list of blank forms. Pick the document that will be used to send the prior authorization.  
4. Run memories search to find the relevant advice and previous successful prior authorizations to maximize the success rate of this prior authorization application.  
5. Call a subagent who fills out the blank form we chose at step 3 using the document population service and the results of the memory search.  
6. Send the filled document using the document courier service.  
7. Once sent, there will be two outcomes: authorization or rejection  
   1. If authorization, clean up. Save relevant learning experiences, what was effective, what was unnecessary.  
   2. If rejection, we leverage the self improvement pipeline to attempt a stronger appeal.

# Services

## Speech to Text

1. The process begins with a recording of a doctor’s appointment that is input into the pipeline.  
2. A speech to text module is used to extract a transcript of the appointment (AWS speech to text)

## Search

You will have to implement a search system for 2 purposes:

1. Search for and choose the relevant forms to populate for prior authorization application.  
2. Search for and choose from relevant memories that would most likely help in the process of filling out the prior authorization form.

## Memories

Memories should have structure to enable searching. At the highest level there should be advice that is relevant for populating any document for any prescription.  
There should be 3 ways to search for more specific memories:

1. Memories connected to document  
2. Memories of provider  
3. Memories of prescription

## Document Population Service

1. Call a lambda function that fills out the blank forms that our LLM can use. It essentially needs to tell the LLM what fields need to be filled and their descriptions, and can take the input from the LLM to fill the fields. When it is done, the filled PDF has to be saved with a traceable labeling scheme. This is because if the form leads to a successful prior authorization, it will be used later as a reference.

## Document Courier Service

Courier Service class is used to send and receive prior auth applications and responses. Route to the proper courier services based on the healthcare providers requirements.  
Fax Service sub class can be configured and used to send fax based authorizations.  
Email Service sub class can be configured and used to send email based authorizations.

## Self improvement pipeline

When a prior authorization is rejected, it often comes back with a description of the reasons for rejections. Using the descriptions, search through the patients’ data to make necessary fixes and resend the prior authorization using the components of the pipeline already described and integrate feedback into additional context that is provided at all stages of the pipeline. On success this feedback should be saved into the memory subsystem.

In the case of a rejection without reasoning provided, we will handle this by proposing potential reasoning in an experimental format. We will iterate through this ranked list of most likely helpful to least likely helpful changes, and use informed guesses to maximize our chances in the appeals process. Given a success using one of these results, we will also save the successful brainstormed change in the memory subsystem.
