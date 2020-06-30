window.app = new Vue({
    el: '#app',
    data: {
        hostname: window.meshping_hostname,
        success_msg: "",
        last_update: 0,
        search: localStorage.getItem("meshping_search") || "",
        targets_all: [],
        targets_filtered: [],
        add_tgt_name: "",
        add_tgt_addr: "",
    },
    methods: {
        update_targets: async function () {
            var response = await this.$http.get('/api/targets');
            var json = await response.json();
            this.targets_all = json.targets;
            this.last_update = new Date();
        },
        reapply_filters: function() {
            if( this.search === "" ){
                // Make a copy of the array, or else chrome goes 100% CPU in sort() :o
                this.targets_filtered = this.targets_all.slice();
            } else {
                var search = this.search.toLowerCase();
                this.targets_filtered = this.targets_all.filter(function(target){
                    return (
                        target.name.toLowerCase().indexOf(search) !== -1 ||
                        target.addr.indexOf(search) !== -1
                    );
                });
            }
            var ip_as_filled_str = function(ipaddr) {
                if (ipaddr.indexOf(":") === -1) {
                    // IPv4
                    return (ipaddr
                        .split(".")
                        .map(x => x.toString().padStart(3, "0"))
                        .join("")
                    );
                } else {
                    // IPv6
                    return (ipaddr
                        .split(":")
                        .map(x => x.toString().padStart(4, "0"))
                        .join("")
                    );
                }
            }
            this.targets_filtered.sort(function(a, b){
                return ip_as_filled_str(a.addr).localeCompare(ip_as_filled_str(b.addr));
            });
        },
        delete_target: async function(target) {
            var message = `Delete target ${target.name} (${target.addr})?`;
            if (confirm(message)) {
                var response = await this.$http.delete(`/api/targets/${target.addr}`);
                var json = await response.json();
                if (json.success) {
                    this.show_success(`<strong>Success!</strong> Deleted target ${target.name} (${target.addr}).`);
                    this.update_targets();
                }
            }
        },
        create_target: async function() {
            var target_str = this.add_tgt_name;
            if (this.add_tgt_addr !== "") {
                target_str += "@" + this.add_tgt_addr;
            }
            var response = await this.$http.post('/api/targets', {
                "target": target_str
            });
            var json = await response.json();
            if (json.success) {
                this.add_tgt_name = "";
                this.add_tgt_addr = "";
                this.show_success(
                    "<strong>Success!</strong> Added targets: <ul>" +
                      json.targets.map(tgt => `<li>${tgt}</li>`).join("") +
                    "</ul>"
                );
                this.update_targets();
            }
        },
        clear_stats: async function() {
            var response = await this.$http.delete('/api/stats');
            var json = await response.json();
            if (json.success) {
                this.show_success(
                    "<strong>Success!</strong>Stats are cleared."
                );
                this.update_targets();
            }
        },
        show_success: function(msg) {
            this.success_msg = msg;
            setTimeout(function(vue){
                vue.success_msg = "";
            }, 5000, this);
        }
    },
    created: function() {
        var self = this;
        window.setInterval(function(vue){
            if( new Date() - vue.last_update > 29500 ){
                vue.update_targets();
            }
        }, 1000, this);
        $(window).keydown(function(ev){
            if (ev.ctrlKey && ev.key === "f") {
                ev.preventDefault();
                $("#inpsearch").focus();
            }
            else if (ev.key === "Escape") {
                $("#inpsearch").blur();
                self.search = "";
            }
        });
    },
    watch: {
        search: function(search) {
            localStorage.setItem("meshping_search", search);
            this.reapply_filters();
        },
        targets_all: function() {
            this.reapply_filters();
        }
    },
    filters: {
        prettyFloat: function(value) {
            if (value === undefined || typeof value.toFixed !== 'function') {
                return '—';
            }
            return value.toFixed(2);
        }
    }
});
