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

  In order to have the visualizer label for each of the defects on the image, label values in json format has to be provided in [etcd_pre_load.json](../docker_setup/provision/config/etcd_pre_load.json) file under "/Visualizer/config" with the mapping between topic subscribed and the label that has to be displayed.

  An example of what this JSON value should look like is shown below. In this case
  it is assumed that the classification types are `0` and `1` and the text labels
  to be displayed are `MISSING` and `SHORT` respectively.

  ```json
  {
      "0": "MISSING",
      "1": "SHORT"
  }
  ```
  > **NOTE:** These labels are the mapping for the PCB demo provided in EIS's visualizer directory. Currently camera1_stream_results consists of pcb demo labeling and camera2_stream_results consists of safety demo labeling.
  Hence, in [etcd_pre_load.json](../docker_setup/provision/config/etcd_pre_load.json), mapping of camera1_stream_results, camera2_stream_results (subscribed topics) has to be done with pcb demo labeling, safety demo labeling respectively.

  ```json
"/WebVisualizer/config": {
        "username": "admin",
        "password": "admin@123",
        "port": 5000,
        "labels" : {
            "camera1_stream": {
                "0": "MISSING",
                "1": "SHORT"
            },
            "camera2_stream_results":{
                "1": "safety_helmet",
                "2": "safety_jacket",
                "3": "Safe",
                "4": "Violation"
            }
        }
    }
    ```



