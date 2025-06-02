odoo.define("pms_helpdesk_portal.form", function () {
    "use strict";

    $(document).ready(function () {
        $("#helpdesk_property").on("change", function () {
            var property_id = $(this).val();
            if (!property_id) return;

            $.ajax({
                url: "/helpdesk/pms/rooms/" + property_id,
                dataType: "json",
                success: function (data) {
                    var $roomSelect = $("#helpdesk_room");
                    $roomSelect
                        .empty()
                        .append('<option value="">Select a room</option>');

                    if (data.length === 0) {
                        $roomSelect.append(
                            "<option disabled>No rooms available</option>"
                        );
                    } else {
                        $.each(data, function (index, room) {
                            $roomSelect.append(
                                '<option value="' +
                                    room.id +
                                    '">' +
                                    room.name +
                                    "</option>"
                            );
                        });
                    }
                },
            });
        });
    });
});
