export default {
    name: 'VueComponentNoMethods',
    data() {
        return {
            message: 'No methods here'
        };
    },
    mounted() {
        console.log('Mounted without methods');
    }
};
