// helpdesk_pms_alda/static/src/js/ticket_form.js

odoo.define("helpdesk_pms_alda.ticket_form", function () {
    "use strict";

    $(document).ready(function () {
        const roomSelect = document.querySelector("[name='room_ids']");
        const locationSelect = document.querySelector("[name='location_type']");
        const bathroomField = document.getElementById("bathroom_field");
        const bathroomSelect = document.querySelector("[name='bathroom_type']");

        if (!locationSelect || !bathroomField) return;

        function handleLocationChange() {
            const selectedLocation = locationSelect.value;

            if (selectedLocation === "bathroom") {
                bathroomField.style.display = "block";
                roomSelect.required = true;
                bathroomSelect.required = true;
            } else if (selectedLocation === "room") {
                bathroomField.style.display = "none";
                bathroomSelect.value = "";
                roomSelect.required = true;
            } else {
                bathroomField.style.display = "none";
                bathroomSelect.value = "";
                roomSelect.required = false;
            }
        }

        // Initialize
        handleLocationChange();
        $(locationSelect).on("change", handleLocationChange);
    });
});
