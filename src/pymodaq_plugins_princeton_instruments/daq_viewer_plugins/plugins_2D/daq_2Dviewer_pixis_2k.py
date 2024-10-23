from pymodaq.utils.daq_utils import ThreadCommand
from pymodaq.utils.data import DataFromPlugins, Axis, DataToExport
from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.parameter import Parameter

from qtpy import QtWidgets, QtCore

from pymodaq_plugins_princeton_instruments.hardware.picam_utils import define_pymodaq_pyqt_parameter, sort_by_priority_list, remove_settings_from_list

import pylablib.devices.PrincetonInstruments as PI

# wrapper already exist via pylablib
#class PythonWrapperOfYourInstrument:
    #  TODO Replace this fake class with the import of the real python wrapper of your instrument
#    pass


# TODO:
# (1) change the name of the following class to DAQ_2DViewer_TheNameOfYourChoice
# (2) change the name of this file to daq_2Dviewer_TheNameOfYourChoice ("TheNameOfYourChoice" should be the SAME
#     for the class name and the file name.)
# (3) this file should then be put into the right folder, namely IN THE FOLDER OF THE PLUGIN YOU ARE DEVELOPING:
#     pymodaq_plugins_my_plugin/daq_viewer_plugins/plugins_2D


class DAQ_2DViewer_pixis_2k(DAQ_Viewer_base):
    """ Instrument plugin class for a 2D viewer.

    This object inherits all functionalities to communicate with PyMoDAQ’s DAQ_Viewer module through inheritance via
    DAQ_Viewer_base. It makes a bridge between the DAQ_Viewer module and the Python wrapper of a particular instrument.

    TODO Complete the docstring of your plugin with:
        * The set of instruments that should be compatible with this instrument plugin.
        * With which instrument it has actually been tested.
        * The version of PyMoDAQ during the test.
        * The version of the operating system.
        * Installation instructions: what manufacturer’s drivers should be installed to make it run?

    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library.

    # TODO add your particular attributes here if any

    """

    camera_list = PI.list_cameras()
    serialnumbers = [device_camera.serial_number for device_camera in camera_list]

    params = comon_parameters + [
        {'title': 'Camera Model:', 'name': 'camera_model', 'type': 'str', 'value': '', 'readonly': True},
        {'title': 'Serial number:', 'name': 'serial_number', 'type': 'list', 'limits': serialnumbers},
        {'title': 'Simple Settings', 'name': 'simple_settings', 'type': 'bool', 'value': True}
    ]

    callback_signal = QtCore.Signal()

    hardware_averaging = False

    def ini_attributes(self):
        #  TODO declare the type of the wrapper (and assign it to self.controller) you're going to use for easy
        #  autocompletion
        self.controller = PI.PicamCamera()

        # TODO declare here attributes you want/need to init with a default value

        self.x_axis = None
        self.y_axis = None

    def _update_all_settings(self):
        """Update all parameters in the interface from the values set in the device.
        Log any detected changes while updating values in the UI."""
        for grandparam in ['settable_camera_parameters', 'read_only_camera_parameters']:
            for param in self.settings.child(grandparam).children():
                # update limits in the parameter
                self.controller.get_attribute(param.title()).update_limits()
                # retrieve a value change in other parameters
                newval = self.controller.get_attribute_value(param.title())
                if newval != param.value():
                    self.settings.child(grandparam, param.name()).setValue(newval)
                    self.emit_status(ThreadCommand('Update_Status', [f'updated {param.title()}: {param.value()}']))

    def _update_rois(self, ):
        """Special method to commit new ROI settings."""
        new_x = self.settings.child('settable_camera_parameters', 'rois', 'x').value()
        new_width = self.settings.child('settable_camera_parameters', 'rois', 'width').value()
        new_xbinning = self.settings.child('settable_camera_parameters', 'rois', 'x_binning').value()

        new_y = self.settings.child('settable_camera_parameters', 'rois', 'y').value()
        new_height = self.settings.child('settable_camera_parameters', 'rois', 'height').value()
        new_ybinning = self.settings.child('settable_camera_parameters', 'rois', 'y_binning').value()

        # In pylablib, ROIs compare as tuples
        new_roi = (new_x, new_width, new_xbinning, new_y, new_height, new_ybinning)
        if new_roi != tuple(self.controller.get_attribute_value('ROIs')[0]):
            # self.controller.set_attribute_value("ROIs",[new_roi])
            self.controller.set_roi(new_x, new_x + new_width, new_y, new_y + new_height, hbin=new_xbinning,
                                    vbin=new_ybinning)
            self.emit_status(ThreadCommand('Update_Status', [f'Changed ROI: {new_roi}']))
            self._update_all_settings()
            self.controller.clear_acquisition()
            self.controller._commit_parameters()  # Needed so that the new ROIs are checked by the camera
            self.controller.setup_acquisition()
            # Finally, prepare view for displaying the new data
            self._prepare_view()

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        # TODO for your custom plugin
        # We have to treat rois specially
        if param.parent().name() == "rois":
            self._update_rois()
        # Otherwise, the other parameters can be dealt with at once
        elif self.controller.get_attribute(param.title()).writable:
            if self.controller.get_attribute_value(param.title()) != param.value():
                # Update the controller
                self.controller.set_attribute_value(param.title(), param.value(), truncate=True, error_on_missing=True)
                # Log that a parameter change was called
                self.emit_status(ThreadCommand('Update_Status', [f'Changed {param.title()}: {param.value()}']))
                self._update_all_settings()


    def emit_data(self):
        """
            Fonction used to emit data obtained by callback.
            See Also
            --------
            daq_utils.ThreadCommand
        """
        try:
            # Get  data from buffer
            frame = self.controller.read_newest_image()
            # Emit the frame.
            self.data_grabed_signal.emit([DataFromPlugins(name='Pixis-2K',
                                                          data=[np.squeeze(frame)],
                                                          dim=self.data_shape,
                                                          labels=[f'Pixis_{self.data_shape}'],
                                                          )])
            #To make sure that timed events are executed in continuous grab mode
            QtWidgets.QApplication.processEvents()

        except Exception as e:
            self.emit_status(ThreadCommand('Update_Status', [str(e), 'log']))


    def ini_detector(self, controller=None):
        """Detector communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator/detector by controller
            (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        #raise NotImplemented  # TODO when writing your own plugin remove this line and modify the one below
        #self.ini_detector_init(slave_controller=controller)
        self.ini_detector_init(old_controller=controller,
                               new_controller=PI.PicamCamera())
        try:
            if self.is_master:
                # Pylablib's PI camera module object
                camera = PI.PicamCamera(self.settings.child('serial_number').value())
                # Set camera name
                self.settings.child('controller_id').setValue(camera.get_device_info().model)
                # init controller
                self.controller = camera

                #self.controller = PythonWrapperOfYourInstrument()  # instantiate you driver with whatever arguments are needed
                #self.controller.open_communication()  # call eventual methods
                # Way to define a wait function with arguments
                wait_func = lambda: self.controller.wait_for_frame(since='lastread', nframes=1, timeout=20.0)
                callback = PicamCallback(wait_func)

                self.callback_thread = QtCore.QThread()  # creation of a Qt5 thread
                callback.moveToThread(self.callback_thread)  # callback object will live within this thread
                callback.data_sig.connect(
                    self.emit_data)  # when the wait for acquisition returns (with data taken), emit_data will be fired

                self.callback_signal.connect(callback.wait_for_acquisition)
                self.callback_thread.callback = callback
                self.callback_thread.start()

                # Get all parameters and sort them in read_only or settable groups
                atd = self.controller.get_all_attributes(copy=True)
                camera_params = []
                for k, v in atd.items():
                    tmp = define_pymodaq_pyqt_parameter(v)
                    if tmp is not None:
                        camera_params.append(tmp)
                #####################################
                read_and_set_parameters = [par for par in camera_params if not par['readonly']]
                read_only_parameters = [par for par in camera_params if par['readonly']]

                # List of priority for ordering the parameters in the UI.
                priority = ['Exposure Time',
                            'ADC Speed',
                            'ADC Analog Gain',
                            'ADC Quality',
                            'ROIs',
                            'Sensor Temperature Set Point',
                            ]
                remove = ['Active Width',
                          'Active Height',
                          'Active Left Margin',
                          'Active Top Margin',
                          'Active Right Margin',
                          'Active Bottom Margin',
                          'Shutter Closing Delay',
                          'Shutter Opening Delay',
                          'Readout Count',
                          'ADC Bit Depth',
                          'Time Stamp Bit Depth',
                          'Frame Tracking Bit Depth',
                          'Shutter Delay Resolution',
                          'Shutter Timing Monde',
                          'Trigger Response',
                          'Trigger Determination',
                          'Output Signal',
                          'Pixel Format',
                          'Invert Output Signal',
                          'Disable Data Formatting',
                          'Track Frames',
                          'Clean Section Final Height',
                          'Clean Section Final Height Count',
                          'Clean Cycle Count',
                          'Clean Cycle Height',
                          'Clean Serial Register',
                          'Clean Until Trigger',
                          'Normalize Orientation',
                          'Correct Pixel Bias',
                          'Shutter Timing Mode',
                          'Time Stamps',
                          'Time Stamp Resolution',
                          ]
                read_and_set_parameters = sort_by_priority_list(read_and_set_parameters, priority)
                if self.settings.child('simple_settings').value():
                    read_and_set_parameters = remove_settings_from_list(read_and_set_parameters, remove)

                # List of priority for ordering the parameters in the UI but for read only params, which is less
                # important (kindof)
                priority = ['Sensor Temperature',
                            'Readout Time Calculation',
                            'Frame Rate Calculation',
                            'Pixel Width',
                            'Pixel Height',
                            ]
                remove = ['Sensor Masked Height',
                          'Sensor Masked Top Margin',
                          'Sensor Masked Bottom Margin',
                          'Gap Width',
                          'Gap Height',
                          'CCD Characteristics',
                          'Exact Readout Count Maximum',
                          'Pixel Width',
                          'Pixel Height',
                          'Frame Size',
                          'Frame Stride',
                          'Pixel Bit Depth',
                          'Sensor Secondary Masked Height',
                          'Sensor Active Width',
                          'Sensor Active Height',
                          'Sensor Active Left Margin',
                          'Sensor Active Top Margin',
                          'Sensor Active Right Margin',
                          'Sensor Active Bottom Margin',
                          'Sensor Secondary Active Height',
                          'Sensor Active Extended Height',
                          'Sensor Temperature Status',
                          'Orientation',
                          'Readout Orientation',
                          'Sensor Type',
                          ]
                read_only_parameters = sort_by_priority_list(read_only_parameters, priority)
                if self.settings.child('simple_settings').value():
                    read_only_parameters = remove_settings_from_list(read_only_parameters, remove)

                # Initialisation of the parameters
                self.settings.addChild({'title': 'Settable Camera Parameters',
                                        'name': 'settable_camera_parameters',
                                        'type': 'group',
                                        'children': read_and_set_parameters,
                                        })
                self.settings.addChild({'title': 'Read Only Camera Parameters',
                                        'name': 'read_only_camera_parameters',
                                        'type': 'group',
                                        'children': read_only_parameters,
                                        })

                # Prepare the viewer (2D by default)
                self._prepare_view()

                self.status.info = "Initialised camera"
                self.status.initialized = True
                self.status.controller = self.controller
                return self.status

        except Exception as e:
            self.emit_status(ThreadCommand('Update_Status', [getLineInfo() + str(e), 'log']))
            self.status.info = getLineInfo() + str(e)
            self.status.initialized = False

        return self.status


        ## TODO for your custom plugin
        # get the x_axis (you may want to to this also in the commit settings if x_axis may have changed
        #data_x_axis = self.controller.your_method_to_get_the_x_axis()  # if possible
        #self.x_axis = Axis(data=data_x_axis, label='', units='', index=1)

        # get the y_axis (you may want to to this also in the commit settings if y_axis may have changed
        #data_y_axis = self.controller.your_method_to_get_the_y_axis()  # if possible
        #self.y_axis = Axis(data=data_y_axis, label='', units='', index=0)

        ## TODO for your custom plugin. Initialize viewers pannel with the future type of data
        #self.dte_signal_temp.emit(DataToExport('myplugin',
        #                                       data=[DataFromPlugins(name='Mock1', data=["2D numpy array"],
        #                                                             dim='Data2D', labels=['dat0'],
        #                                                             axes=[self.x_axis, self.y_axis]), ]))

        #info = "Whatever info you want to log"
        #initialized = True
        #return info, initialized

    def close(self):
        """Terminate the communication protocol"""
        ## TODO for your custom plugin
        #raise NotImplemented  # when writing your own plugin remove this line
        #  self.controller.your_method_to_terminate_the_communication()  # when writing your own plugin replace this line
        # Terminate the communication
        self.controller.close()
        self.controller = None  # Garbage collect the controller
        # Clear all the parameters
        self.settings.child('settable_camera_parameters').clearChildren()
        self.settings.child('settable_camera_parameters').remove()
        self.settings.child('read_only_camera_parameters').clearChildren()
        self.settings.child('read_only_camera_parameters').remove()
        # Reset the status of the Viewer Plugin
        self.status.initialized = False
        self.status.controller = None
        self.status.info = ""


    def _toggle_non_online_parameters(self, enabled):
        """All parameters that cannot be changed while acquisition is on can be automatically
        enabled or disabled. Note that I have no idea if pymodaq supports this can of things by
        default but at least that's already implemented..."""
        for param in self.settings.child('settable_camera_parameters').children():
            if not self.controller.get_attribute(param.title()).can_set_online:
                param.setOpts(enabled=enabled)
        # The ROIs parameters still need special treatment which is not ideal but well...
        for param in self.settings.child('settable_camera_parameters', "rois").children():
            param.setOpts(enabled=enabled)

    def _prepare_view(self):
        """Preparing a data viewer by emitting temporary data. Typically, needs to be called whenever the
        ROIs are changed"""
        wx = self.settings.child('settable_camera_parameters', 'rois', 'width').value()
        wy = self.settings.child('settable_camera_parameters', 'rois', 'height').value()
        bx = self.settings.child('settable_camera_parameters', 'rois', 'x_binning').value()
        by = self.settings.child('settable_camera_parameters', 'rois', 'y_binning').value()

        sizex = wx // bx
        sizey = wy // by

        mock_data = np.zeros((sizey, sizex))

        if sizey != 1 and sizex != 1:
            data_shape = 'Data2D'
        else:
            data_shape = 'Data1D'

        if data_shape != self.data_shape:
            self.data_shape = data_shape
            # init the viewers
            self.data_grabed_signal_temp.emit([DataFromPlugins(name='Picam',
                                                               data=[np.squeeze(mock_data)],
                                                               dim=self.data_shape,
                                                               labels=[f'Picam_{self.data_shape}'])])
            QtWidgets.QApplication.processEvents()

    def grab_data(self, Naverage=1, **kwargs):
        """Start a grab from the detector

        Parameters
        ----------
        Naverage: int
            Number of hardware averaging (if hardware averaging is possible, self.hardware_averaging should be set to
            True in class preamble and you should code this implementation)
        kwargs: dict
            others optionals arguments
        """
        ## TODO for your custom plugin: you should choose EITHER the synchrone or the asynchrone version following

        ##synchrone version (blocking function)
        #data_tot = self.controller.your_method_to_start_a_grab_snap()
        #self.dte_signal.emit(DataToExport('myplugin',
        #                                  data=[DataFromPlugins(name='Mock1', data=data_tot,
        #                                                        dim='Data2D', labels=['label1'],
        #                                                        x_axis=self.x_axis,
        #                                                        y_axis=self.y_axis), ]))

        ##asynchrone version (non-blocking function with callback)
        #self.controller.your_method_to_start_a_grab_snap(self.callback)
        #########################################################
        try:
            # Warning, acquisition_in_progress returns 1,0 and not a real bool
            if not self.controller.acquisition_in_progress():
                # 0. Disable all non online-settable parameters
                self._toggle_non_online_parameters(enabled=False)
                # 1. Start acquisition
                self.controller.clear_acquisition()
                self.controller.start_acquisition()
            #Then start the acquisition
            self.callback_signal.emit()  # will trigger the wait for acquisition

        except Exception as e:
            self.emit_status(ThreadCommand('Update_Status', [str(e), "log"]))

    def callback(self):
        """optional asynchrone method called when the detector has finished its acquisition of data"""
        raise NotImplementedError
        #data_tot = self.controller.your_method_to_get_data_from_buffer()
        #self.dte_signal.emit(DataToExport('pixis_2K',
        #                                  data=[DataFromPlugins(name='Pixis_2K', data=data_tot,
        #                                                        dim='Data2D', labels=['label1'],
        #                                                        x_axis=self.x_axis,
        #                                                        y_axis=self.y_axis), ]))

    def stop(self):
        """Stop the current grab hardware wise if necessary"""
        ## TODO for your custom plugin
        #raise NotImplemented  # when writing your own plugin remove this line
        #self.controller.your_method_to_stop_acquisition()  # when writing your own plugin replace this line

        ##############################
        self.controller.stop_acquisition()
        self.controller.clear_acquisition()
        self._toggle_non_online_parameters(enabled=True)
        self.emit_status(ThreadCommand('Update_Status', ['Stop Pixis_2K camera']))
        return ''


class PicamCallback(QtCore.QObject):
    """Callback object for the picam library"""
    data_sig = QtCore.Signal()
    def __init__(self,wait_fn):
        super().__init__()
        #Set the wait function
        self.wait_fn = wait_fn

    def wait_for_acquisition(self):
        new_data = self.wait_fn()
        if new_data is not False: #will be returned if the main thread called CancelWait
            self.data_sig.emit()


if __name__ == '__main__':
    main(__file__)