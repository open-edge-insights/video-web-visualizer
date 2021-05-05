# Intel Edge Insights Web Visualizer
Web Visualizer ia a web based app to view the classified images/metadata coming out of EII.


#### Steps to build and run web viualizer

* Follow [provision/README.md](../README#provision.md) for Provisioning
  if not done already as part of EII stack setup

* Running visualizer as a container from [build](../../build):

  ```
    $ docker-compose -f docker-compose-build.yml build ia_web_visualizer
    $ docker-compose up ia_web_visualizer
  ```

* Running Visualizer in Browser

  * Visualizer is tested on Chrome Browser. Its better to use chrome browser.
  * WebVisualizer Currently supports Only **6** parallel streams in the chrome browser per instance.

  #### DEV mode
    * Goto Browser
        http://< host ip >:5001

  #### PROD Mode:
    * copy 'ca_certificate.pem' from 'build/provision/Certificates/ca' to home directory '~/'
      and give appropriate permissions to it as shown below:

    ```
        $ sudo cp Certificates/ca/ca_certificate.pem ~
        $ cd ~
        $ sudo chmod 0755 ~/ca_certificate.pem
    ```

    * Import 'ca_certificate.pem' from home Directory '~/' to your Browser Certifcates.

      ##### Steps to Import Certificates
        * Goto *Settings* in Chrome
        * Search *Manage Certificates* Under Privacy & Security
        * Select Manage Certificates Option
        * Under *Authorities* Tab Click Import Button
        * With Import Wizard navigate to home directory
        * Select *ca_certificate.pem* file
        * Select All CheckBoxes and Click Import Button.

    * Now In Browser
        https://< host ip >:5000

    * Login Page
        You should use your defined username & password in etcd config.
-----
**NOTE**:
1. The admin has to make sure all the necessary config is set in etcd before starting the web visualizer.
2. Please clear your `browsers cache` while switching from `prod` mode to `dev` mode on running 
`WebVisualizer` in browser.

#### Using Labels

  In order to have the web visualizer label each of the defects on the image, labels in JSON format(with mapping between topic subscribed text to be displayed) has to be provided in [config.json](./config.json) file and run the [builder.py](../build/builder.py) script using the below command.
  ```sh
  $ python3 builder.py
  ```

  An example of what this JSON value should look like is shown below. In this case
  it is assumed that the classification types are `0` and `1` and the text labels
  to be displayed are `MISSING` and `SHORT` respectively.

  ```json
  {
      "0": "MISSING",
      "1": "SHORT"
  }
  ```
  > **NOTE:** These labels are the mapping for the PCB demo provided in EII's web visualizer directory. Currently camera1_stream_results consists of pcb demo labeling and camera2_stream_results consists of safety demo labeling.
  Hence, in [config.json](./config.json), mapping of all the subscribed topics has to be done with pcb demo labeling and safety demo labeling respectively.

  ```json
"/WebVisualizer/config": {
        "username": "admin",
        "password": "admin@123",
        "dev_port": 5001,
        "port": 5000,
        "labels" : {
            "camera1_stream": {
                "0": "MISSING",
                "1": "SHORT"
            },
            "native_safety_gear_stream_results": {
                "1": "safety_helmet",
                "2": "safety_jacket",
                "3": "Safe",
                "4": "Violation"
            },
            "py_safety_gear_stream_results": {
                "1": "safety_helmet",
                "2": "safety_jacket",
                "3": "Safe",
                "4": "Violation"

            },
            "gva_safety_gear_stream_results": {
                "1": "safety_helmet",
                "2": "safety_jacket",
                "3": "Safe",
                "4": "Violation"
            }

        }
    }
```

### Metadata Structure

EII WebVisualizer app can decode certain types of mete-data formats for drawing the defects on the image.
Any application wanting to use EII WebVisualizer need to comply with the meta-data format as described below:

A) For Ingestor's **Non-GVA** type, metadata structure sample is :

```json
{
 'channels': 3,
 'encoding_type': 'jpeg',
 'height': 1200,

 'defects': [
     {'type': 0, 'tl': [1019, 644], 'br': [1063, 700]},
     {'type': 0, 'tl': [1297, 758], 'br': [1349, 796]}
    ],

'display_info': [{'info':'good', 'priority':0}],

'img_handle': '348151d424',
'width': 1920,
'encoding_level': 95
}
```

where in `defects` and `display_info` is a list of dicts.

Each entry in `defects` list is a dictionary that should contain following keys:
* `type` : value given to type will be the label id
* `tl` : value is the top-left `x` and `y` co-ordinate of the defect in the image.
* `br` : value is the bottom-right `x` and `y` co-ordinate of the defect in the image.

Each entry in `display_info` list is a dictionary that should contain following keys:
* `info` : value given will be displayed on the image.
* `priority` : Based on the priority level (0, 1, or 2), info will be displayed in either green, orange or red.
    * 0 : Low priority, info will be displayed in green.
    * 1 : Medium priority, info will be displayed in orange.
    * 2 : High priority, info will be displayed in red.

----
B) For Ingestor's **GVA** type, metadata structure sample is :

```json
{
    'channels': 3,
    'gva_meta': [

        {'x': 1047, 'height': 86, 'y': 387, 'width': 105, 'tensor': [{'label': '', 'label_id': 1, 'confidence':0.8094226121902466, 'attribute':'detection'}]},

        {'x': 1009, 'height': 341, 'y': 530, 'width': 176, 'tensor': [{'label': '', 'label_id': 2, 'confidence': 0.9699158668518066, 'attribute': 'detection'}]}

        ],

    'encoding_type': 'jpeg',
    'height': 1080,
    'img_handle': '7247149a0d',
    'width': 1920,
    'encoding_level': 95
}

```
where in `gva_meta` is a list of dicts.

**NOTE**:

1) Any data with in the list, tuple or dict of meta data should be of primitive data type (int, float, string, bool). Refer the examples given above.

2)If user needs to remove the bounding box:

  Set the value of draw_results in config.json as false for both Visualiser and WebVisualiser.

    ```
    draw_results: "false"
    ```

