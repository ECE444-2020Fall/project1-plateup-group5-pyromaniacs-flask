# PlateUp API Service

Hello! Welcome to PlateUp's API service submodule.

###### Main Repo: https://github.com/ECE444-2020Fall/project1-plateup-group5-pyromaniacs

###### Heroku API service (staging): https://sheltered-thicket-73220.herokuapp.com/

This is a submodule of the PlateUp main repo, all development instructions are available in the main repo. This submodule was created near beta release to facilitate heroku staging deployment, and to better track issues and update documentation. 

 
## OpenAPI (formerly swagger) documentation overview 
Please see our [Wiki](https://github.com/ECE444-2020Fall/project1-plateup-group5-pyromaniacs-flask/wiki)

## Testing on APIS
Currently the unit testing implemented on backend covers 73% of the code. Here is the results:

Name                Stmts   Miss  Cover
---------------------------------------
background.py          17     12    29%
emailservice.py        21     17    19%
initializer.py         22      0   100%
models.py              77      0   100%
run.py                412    116    72%
schemas.py             16      0   100%
tests\__init__.py       0      0   100%
tests\run_test.py     170     16    91%
util.py                71     59    17%
---------------------------------------
TOTAL                 806    220    73%

The team is trying to let the test to covers more codes. Since the back end system on this project is very large and the time limit is short, the team cannot covers all code. But the team will try to implement more unit test to cover the code on the backend in future release

## Why use OpenAPI spec and swagger documentation?
OpenAPI is the group's choice for a backend to frontend hand-off tool, but also follows an industry standard for development against APIs. Due to PlateUp's achitecture as a server-client application, the functionality of backend services must be testable separately from the frontend application. As such, OpenAPI documentation allows us to excessively document all our endpoints and routes, as well as test it as shown in the gifs above. Coupled with our unit tests, this form of integration testing really ensures good application quality. 

One further example of the documentation that OpenAPI offers is defining models (the request/response structures) clearly for front-end devs:

<p align="center">
<img alt="Showcasing models documentation on OpenAPI" src="documentation/models_showcase.gif" width="90%" align="center"/>
</p> 
                                                                                                                           
  
## Future Improvements
There is still a lot of work to be done on the backend service. Some are feature focused, such as expanding shopping/flash functionality, adding the ability to get and delete individual users rather than clearing all users, etc. Others are bug focused, such as supporting multiple consecutive recipe checks without adding ingredients to a user's shopping list multiple times. Still, others include potentially open-sourcing this API, because it is written in clear, well-documented code and uses the OpenAPI standard, which allows it to become a public-facing API (other versions of PlateUp or Chef's CoPilot can develop against it) without too much effort. For all of these goals, more development effort and time is required.
