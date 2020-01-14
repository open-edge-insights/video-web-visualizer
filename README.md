# Intel Edge Insights Web Visualizer
Web Visualizer ia a web based app to view the classified images/metadata coming out of EIS.


#### Steps to build and run viualizer

* Follow [provision/README.md](../README#provision-eis.md) for EIS provisioning
  if not done already as part of EIS stack setup

* Running visualizer as a container from [docker_setup](../../docker_setup):

  ```
    $ docker-compose up --build ia_web_visualizer
  ```

* Running Visualizer in Browser

  * Visualizer is tested on Chrome Browser. Its better to use chrome browser.
  * WebVisualizer Currently supports Only **6** parallel streams in the chrome browser per instance.

  #### DEV mode
    * Goto Browser
        http://localhost:5000

  #### PROD Mode:
    * Import 'ca_certificate.pem' from 'docker_setup/provision/Certificates/ca' Directory to your Browser Certifcates.

      ##### Steps to Import Certificates
        * Goto *Settings* in Chrome
        * Search *Manage Certificates* Under Privacy & Security
        * Select Manage Certificates Option
        * Under *Authorities* Tab Click Import Button
        * With Import Wizard navigate to 
          *IEdgeInsights/docker_setup/provision/Certificates/ca* Dir
        * Select *ca_certificate.pem* file
        * Select All CheckBoxes and Click Import Button.

    * Now In Browser
        https://localhost:5000

    * Login Page
        You should use your defined username & password in etcd config.
-----
**NOTE**:
1. The admin has to make sure all the necessary config is set in etcd before starting the web visualizer.

#### Using Labels

  In order to have the visualizer label each of the defects on the image (i.e.
  text underneath of the bounding box), you will need to provide a JSON file with
  the mapping between the classfication type and the text you wish to display.

  An example of what this JSON file should look like is shown below. In this case
  it is assumed that the classification types are `0` and `1` and the text labels
  to be displayed are `MISSING` and `SHORT` respectively.

  ```json
  {
      "0": "MISSING",
      "1": "SHORT"
  }
  ```
  > **NOTE:** These labels are the mapping for the PCB demo provided in EIS's visualizer directory. Currently pcb_demo_label.json and safety_demo_label.json files are provided for reference.

  An important thing to note above, is that the keys need to still be strings.
  The visualizer will take care of the conversion when it receives publications
  for classification results.

  In case the user running visualizer as a docker container, the visualizer section in [docker-compose.yml](../docker_setup/docker-compose.yml) file should be changed in order to process the labels from a specific JSON file. The ***command*** variable in docker-compose.yml file can be changed as below for using safety_demo_label.json instead of default json file:
  

  Before
  ```json
  ia_visualizer:
  depends_on:
    - ia_common
  -----snip-----
  command: ["pcb_demo_label.json"]
  -----snip-----

  ```
  After
  ```json
  ia_visualizer:
  depends_on:
  - ia_common
  -----snip-----
  command: ["safety_demo_label.json"]
  -----snip-----
  ```

Passing this json file as command line option has been taken care in corrsponding Docker file.


