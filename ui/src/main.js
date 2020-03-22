var app = new Vue({
    el: '#app',
    data: {
        last_update: 0,
        targets: [],
    },
    methods: {
        update_targets: async function () {
            var response = await this.$http.get('/api/targets');
            var json = await response.json();
            this.targets = json.targets;
            this.last_update = new Date();
        }
    },
    created: function() {
        window.setInterval(function(vue){
            if( new Date() - vue.last_update > 29500 ){
                vue.update_targets();
            }
        }, 1000, this);
    }
});
