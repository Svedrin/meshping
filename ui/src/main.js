var app = new Vue({
    el: '#app',
    data: {
        last_update: 0,
        search: localStorage.getItem("meshping_search") || "",
        targets_all: [],
        targets_filtered: [],
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
                this.targets_filtered = this.targets_all;
            } else {
                var search = this.search;
                this.targets_filtered = this.targets_all.filter(function(target){
                    return (
                        target.name.indexOf(search) !== -1 ||
                        target.addr.indexOf(search) !== -1
                    );
                });
            }
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
    }
});
