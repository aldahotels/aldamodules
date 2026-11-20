odoo.define("alda_helpdesk_pms.ticket_attachments", function () {
    "use strict";

    $(document).ready(function () {
        const fileInput = document.getElementById("attachment");
        const submitBtn = document.querySelector("button[type='submit']");
        const warningDiv = document.getElementById("file-warnings");
        const fileListContainer = document.getElementById("file-list");
        const clearAllBtn = document.getElementById("clearAllFilesBtn");

        let accumulatedFiles = [];

        if (fileInput && submitBtn && warningDiv && fileListContainer) {
            const MAX_FILE_SIZE = 10 * 1024 * 1024;
            const MAX_TOTAL_SIZE = 15 * 1024 * 1024;
            const MAX_FILES = 5;

            const refreshInputFiles = () => {
                const dt = new DataTransfer();
                accumulatedFiles.forEach((f) => dt.items.add(f));
                fileInput.files = dt.files;
            };

            const updateFileList = () => {
                fileListContainer.innerHTML = "";
                let totalSize = 0;
                let valid = true;

                if (accumulatedFiles.length > 0) {
                    const header = document.createElement("h6");
                    header.className = "mt-2 mb-2 fw-bold";
                    header.textContent = "Files List to send:";
                    fileListContainer.appendChild(header);
                }

                accumulatedFiles.forEach((file, index) => {
                    totalSize += file.size;

                    const fileRow = document.createElement("div");
                    fileRow.className =
                        "file-item d-flex justify-content-between align-items-center mb-1";

                    fileRow.innerHTML = `
                        <span>${file.name} (${(file.size / 1024 / 1024).toFixed(
                        2
                    )} MB)</span>
                        <button type="button" data-index="${index}" class="remove-file btn btn-sm btn-danger">
                            <i class="fa fa-trash"></i>
                        </button>
                    `;

                    fileListContainer.appendChild(fileRow);

                    if (file.size > MAX_FILE_SIZE) {
                        warningDiv.innerHTML = `
                            <div class="alert alert-danger mt-2">
                                The file <strong>${file.name}</strong> exceeds the 10 MB limit.
                            </div>`;
                        valid = false;
                    }
                });

                // VALIDACIÓN: SOLO UN VIDEO PERMITIDO
                const videoCount = accumulatedFiles.filter((f) =>
                    f.type.startsWith("video/")
                ).length;
                if (valid && videoCount > 1) {
                    warningDiv.innerHTML = `
                        <div class="alert alert-danger mt-2">
                            Only one video file is allowed.
                        </div>`;
                    valid = false;
                }

                if (valid && totalSize > MAX_TOTAL_SIZE) {
                    warningDiv.innerHTML = `
                        <div class="alert alert-warning mt-2">
                            The total size of the files (${(
                                totalSize /
                                1024 /
                                1024
                            ).toFixed(2)} MB) exceeds the allowed limit of 15 MB.
                        </div>`;
                    valid = false;
                } else if (valid) {
                    warningDiv.innerHTML = "";
                }

                submitBtn.disabled = !valid;

                fileListContainer.querySelectorAll(".remove-file").forEach((btn) => {
                    btn.addEventListener("click", () => {
                        const index = parseInt(btn.dataset.index, 10);
                        accumulatedFiles.splice(index, 1);
                        refreshInputFiles();
                        updateFileList();
                    });
                });
            };

            fileInput.addEventListener("change", () => {
                const newlySelected = Array.from(fileInput.files);

                // Check max number of files
                if (accumulatedFiles.length + newlySelected.length > MAX_FILES) {
                    warningDiv.innerHTML = `
                        <div class="alert alert-warning mt-2">
                            You can upload a maximum of ${MAX_FILES} files.
                        </div>`;
                    fileInput.value = "";
                    return;
                }

                // VALIDACIÓN: SOLO UN VIDEO PERMITIDO
                const currentVideoCount = accumulatedFiles.filter((f) =>
                    f.type.startsWith("video/")
                ).length;
                const newVideoCount = newlySelected.filter((f) =>
                    f.type.startsWith("video/")
                ).length;

                if (currentVideoCount + newVideoCount > 1) {
                    warningDiv.innerHTML = `
                        <div class="alert alert-danger mt-2">
                            Only one video file is allowed.
                        </div>`;
                    fileInput.value = "";
                    return;
                }

                accumulatedFiles = accumulatedFiles.concat(newlySelected);

                refreshInputFiles();
                updateFileList();
            });

            if (clearAllBtn) {
                clearAllBtn.addEventListener("click", () => {
                    accumulatedFiles = [];
                    refreshInputFiles();
                    updateFileList();
                });
            }
        }
    });
});
