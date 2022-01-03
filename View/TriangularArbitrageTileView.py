import dearpygui.dearpygui as dpg

dpg.create_context()


with dpg.window(label="Price Discrepency Tile View", tag="Primary Window"):
    t1 = dpg.add_text("Hello, world", tag="Example")
    dpg.add_button(label="Save")
    dpg.add_input_text(label="string", default_value="Quick brown fox")
    dpg.add_slider_float(label="float", default_value=0.273, max_value=1)

dpg.create_viewport(title='Arbitrage', width=600, height=300)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.set_primary_window("Primary Window", True)
dpg.start_dearpygui()
dpg.destroy_context()