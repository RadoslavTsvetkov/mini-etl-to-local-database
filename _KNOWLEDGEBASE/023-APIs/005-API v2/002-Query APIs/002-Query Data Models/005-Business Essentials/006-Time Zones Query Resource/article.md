# Time Zones Query Resource

Last Modified: 2021-10-26 | Code: APIBETZ

To see the available time zones use the "/APIv2/Query/BusinessEssentials/TimeZones" dataset. The dataset can be executed without supplying values for the parameters.

### Shopmetrics CMS UI — Dataset Execution

![](assets/img_01.jpg)

### Postman

The content for the “post” parameter in the Body:

{"action":"exec","dataset":{"datasetname":"/Apps/SM/APIv2/Query/BusinessEssentials/TimeZones"},"parameters":[{"name":"SecurityObjectUserID","value":null},{"name":"MiscSettings","value":null}]}

![](assets/img_02.jpg)
