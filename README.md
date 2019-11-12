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
  * 

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

  #### DEV mode

    * Goto Browser
        http://localhost:5000
-----
**NOTE**:
1. The admin has to make sure all the necessary config is set in etcd before starting the web visualizer.




